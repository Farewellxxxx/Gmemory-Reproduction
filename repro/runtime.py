"""Persistent cost reservations and a non-streaming OpenAI-compatible adapter."""
from datetime import datetime, timezone
import inspect
import json
import math
import os
from pathlib import Path
import re
import time
import uuid

from filelock import FileLock


class RunHalted(BaseException):
    """Stop the experiment, bypassing upstream broad retry/parse catches."""


class RetryableAPIError(RunHalted):
    """An already logged transport error; only the bounded adapter may retry."""


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def redact(value):
    text = str(value)
    secret = os.getenv('OPENAI_API_KEY')
    if secret:
        text = text.replace(secret, '[REDACTED]')
    return re.sub(r'sk-[A-Za-z0-9_-]{16,}', '[REDACTED]', text)


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(redact(json.dumps(value, ensure_ascii=False, indent=2)), encoding='utf-8')
    temp.replace(path)


def append_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a', encoding='utf-8') as stream:
        stream.write(redact(json.dumps(value, ensure_ascii=False)) + '\n')


class Budget:
    """Prices are CA / million tokens, not the upstream hardcoded USD prices.

    A reservation survives crashes/network failures until valid usage settles it.
    Pending amounts are conservative estimates, never described as settled bills.
    """
    def __init__(self, path, limit_ca, deadline_utc=None,
                 input_per_million=1.05, output_per_million=4.2):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = FileLock(str(self.path) + '.lock', timeout=5)
        for value in [limit_ca, input_per_million, output_per_million]:
            if not math.isfinite(value) or value <= 0:
                raise ValueError('Budget and prices must be positive and finite')
        with self.lock:
            if self.path.exists():
                self._read()
                if (self.state['limit_ca'],self.state['input_per_million'],self.state['output_per_million']) != (limit_ca,input_per_million,output_per_million):
                    raise ValueError('Existing budget/prices cannot be reset or changed')
            else:
                if deadline_utc is None:
                    raise ValueError('A new budget requires an explicit deadline')
                deadline = datetime.fromisoformat(deadline_utc)
                if deadline.tzinfo is None:
                    raise ValueError('Deadline must include timezone')
                self.state = dict(limit_ca=limit_ca, deadline_utc=deadline_utc,
                                  input_per_million=input_per_million,output_per_million=output_per_million,
                                  spent_ca=0.0,prompt_tokens=0,completion_tokens=0,
                                  settled_calls=0,pending={},created_utc=utc_now())
                self._save()

    def _read(self):
        self.state = json.loads(self.path.read_text(encoding='utf-8'))

    def _save(self):
        write_json(self.path, self.state)

    def cost(self, prompt, completion):
        return (prompt*self.state['input_per_million'] + completion*self.state['output_per_million'])/1_000_000

    def reserve(self, input_upper, output_max):
        if input_upper < 0 or output_max <= 0:
            raise ValueError('Invalid token reservation')
        with self.lock:
            self._read()
            if datetime.now(timezone.utc) >= datetime.fromisoformat(self.state['deadline_utc']):
                raise RunHalted('Experiment deadline reached')
            amount = self.cost(input_upper, output_max)
            committed = self.state['spent_ca'] + sum(self.state['pending'].values())
            if committed + amount > self.state['limit_ca']:
                raise RunHalted('API budget exhausted before request')
            identifier = uuid.uuid4().hex
            self.state['pending'][identifier] = amount
            self._save()
            return identifier

    def settle(self, identifier, prompt, completion):
        if not isinstance(prompt,int) or not isinstance(completion,int) or min(prompt,completion)<0:
            raise RunHalted('Missing or invalid API usage; reservation retained')
        with self.lock:
            self._read()
            if identifier not in self.state['pending']:
                raise RunHalted('Unknown or already settled call')
            self.state['pending'].pop(identifier)
            amount = self.cost(prompt,completion)
            self.state['spent_ca'] += amount
            self.state['prompt_tokens'] += prompt
            self.state['completion_tokens'] += completion
            self.state['settled_calls'] += 1
            self._save()
            if self.state['spent_ca'] > self.state['limit_ca']:
                raise RunHalted('Reported usage exceeded budget estimate; stopped')
            return amount


class TrackedLLM:
    def __init__(self,budget,log_path,model='gpt-4o-mini',client=None,max_attempts=3,retry_backoff=2):
        if not isinstance(max_attempts,int) or not 1<=max_attempts<=3:
            raise ValueError('At most three transport attempts are permitted')
        if not math.isfinite(retry_backoff) or not 0<=retry_backoff<=5:
            raise ValueError('Retry backoff must be between zero and five seconds')
        self.budget,self.log_path,self.model_name = budget,Path(log_path),model
        self.max_attempts,self.retry_backoff=max_attempts,retry_backoff
        self.attempts_count=0
        self.task_id = None
        self.arm = None
        if client is None:
            from openai import OpenAI
            client = OpenAI(base_url=os.environ['OPENAI_API_BASE'],
                            api_key=os.environ['OPENAI_API_KEY'],timeout=45,max_retries=0)
        self.client = client

    def __call__(self,messages,temperature=0.1,max_tokens=512,stop_strs=None,num_comps=1):
        max_tokens = 512 if max_tokens is None else max_tokens
        num_comps = 1 if num_comps is None else num_comps
        temperature = 0.1 if temperature is None else temperature
        if not isinstance(max_tokens,int) or not 1 <= max_tokens <= 512 or num_comps != 1:
            raise RunHalted('Reproduction permits one completion of at most 512 tokens')
        payload = [dict(role=m.role,content=m.content) for m in messages]
        funcs = [frame.function for frame in inspect.stack()[:12]]
        purpose = next((f for f in funcs if f in ['_extract_mas_message','_detect_mistakes',
                       'project_insights','_finetune_insights','_merge_rules','retrieve_memory']), 'agent_action')
        logical_call_id=uuid.uuid4().hex
        for attempt in range(1,self.max_attempts+1):
            try:
                return self._attempt(payload,temperature,max_tokens,stop_strs,purpose,logical_call_id,attempt)
            except RetryableAPIError:
                if attempt==self.max_attempts:
                    raise RunHalted('Transient API retries exhausted; unresolved reservations retained') from None
                time.sleep(self.retry_backoff*attempt)

    def _attempt(self,payload,temperature,max_tokens,stop_strs,purpose,logical_call_id,attempt):
        # Byte fallback gives a conservative tokenizer bound; allow framing overhead.
        input_upper = len(json.dumps(payload,ensure_ascii=False).encode('utf-8')) + 1024
        call_id = self.budget.reserve(input_upper,max_tokens)
        self.attempts_count+=1
        row = dict(call_id=call_id,time_utc=utc_now(),arm=self.arm,task_id=self.task_id,
                   logical_call_id=logical_call_id,attempt=attempt,max_attempts=self.max_attempts,
                   purpose=purpose,model_requested=self.model_name,messages=payload,
                   max_tokens=max_tokens,temperature=temperature,stop=stop_strs)
        started = time.monotonic()
        try:
            response = self.client.chat.completions.create(
                model=self.model_name,messages=payload,max_tokens=max_tokens,
                temperature=temperature,n=1,stop=stop_strs)
            if response.usage is None:
                raise RunHalted('Missing API usage; reservation retained')
            prompt,completion = response.usage.prompt_tokens,response.usage.completion_tokens
            row['usage'] = dict(prompt_tokens=prompt,completion_tokens=completion)
            row['estimated_ca'] = self.budget.settle(call_id,prompt,completion)
            row['model_returned'] = response.model
            row['response_id'] = response.id
            row['finish_reason'] = response.choices[0].finish_reason
            answer = response.choices[0].message.content
            row['answer'] = answer
            if not isinstance(answer,str) or not answer.strip():
                raise RunHalted('Empty API answer; experiment interrupted')
            row['status'] = 'ok'
            return answer
        except RunHalted as exc:
            row.update(status='error',error=redact(exc))
            raise
        except Exception as exc:
            from openai import APIConnectionError
            status=getattr(exc,'status_code',None)
            row.update(status='error',error_type=type(exc).__name__,
                       http_status=status)
            transient=isinstance(exc,(APIConnectionError,TimeoutError,ConnectionError)) or status==429 or (isinstance(status,int) and status>=500)
            if transient and 'usage' not in row:
                raise RetryableAPIError(f'Transient API failure ({type(exc).__name__})') from None
            raise RunHalted(f'API interrupted ({type(exc).__name__}); see usage ledger') from None
        finally:
            row['elapsed_seconds'] = round(time.monotonic()-started,3)
            append_json(self.log_path,row)
