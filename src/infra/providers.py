"""Provider adapters for the existing tool loop. SDK retry is disabled."""
from __future__ import annotations

import json
from types import SimpleNamespace


def _content(parts):
    if isinstance(parts,str):
        return parts
    out=[]
    for raw in parts or []:
        p=_mapping(raw)
        if p.get('type')=='text':
            out.append({'type':'text','text':p['text']})
        elif p.get('type')=='image':
            source=p['source']
            out.append({'type':'image_url','image_url':{'url':'data:'+source['media_type']+';base64,'+source['data']}})
    return out or ''


class OpenAIAdapter:
    def __init__(self,client=None):
        if client is None:
            from openai import OpenAI
            client=OpenAI(max_retries=0,timeout=120)
        self.client=client
        self.messages=self

    def create(self,*,model,system,messages,tools,max_tokens,**_):
        if hasattr(self.client,'responses'):
            return self._responses(model,system,messages,tools,max_tokens)
        converted=[{'role':'system','content':_content(system)}]
        for message in messages:
            parts=message.get('content',[])
            if message['role']=='assistant':
                calls=[]
                text=[]
                for raw in parts if isinstance(parts,list) else []:
                    p=_mapping(raw)
                    if p.get('type')=='tool_use':
                        calls.append({'id':p['id'],'type':'function','function':{'name':p['name'],'arguments':json.dumps(p['input'],ensure_ascii=False)}})
                    elif p.get('type')=='text':
                        text.append(p['text'])
                item={'role':'assistant','content':'\n'.join(text) or None}
                if calls:
                    item['tool_calls']=calls
                converted.append(item)
            else:
                ordinary=[]
                for raw in parts if isinstance(parts,list) else []:
                    p=_mapping(raw)
                    if p.get('type')=='tool_result':
                        parts=p['content']
                        if isinstance(parts,list) and any(_mapping(x).get('type')=='image' for x in parts):
                            # Chat tool messages accept text only. Keep the
                            # receipt and put the actual page in the next user
                            # message, after all tool calls are acknowledged.
                            caption='\n'.join(_mapping(x).get('text','') for x in parts if _mapping(x).get('type')=='text')
                            converted.append({'role':'tool','tool_call_id':p['tool_use_id'],'content':'Página disponível na mensagem seguinte. '+caption})
                            ordinary.extend(_mapping(x) for x in parts)
                        else:
                            converted.append({'role':'tool','tool_call_id':p['tool_use_id'],'content':_content(parts)})
                    else:
                        ordinary.append(p)
                if ordinary or isinstance(parts,str):
                    converted.append({'role':'user','content':_content(parts if isinstance(parts,str) else ordinary)})
        response=self.client.chat.completions.create(
            model=model,messages=converted,max_completion_tokens=max_tokens,service_tier='default',
            tools=[{'type':'function','function':{'name':t['name'],'description':t['description'],'parameters':t['input_schema']}} for t in tools])
        choice=response.choices[0]
        blocks=[]
        if choice.message.content:
            blocks.append(SimpleNamespace(type='text',text=choice.message.content))
        for call in choice.message.tool_calls or []:
            try:
                arguments=json.loads(call.function.arguments)
            except json.JSONDecodeError:
                arguments={'_invalid_json':call.function.arguments}
            blocks.append(SimpleNamespace(type='tool_use',name=call.function.name,input=arguments,id=call.id))
        usage=None
        if response.usage is not None:
            cached=int(getattr(getattr(response.usage,'prompt_tokens_details',None),'cached_tokens',0) or 0)
            written=int(getattr(getattr(response.usage,'prompt_tokens_details',None),'cache_creation_tokens',0) or 0)
            usage=SimpleNamespace(input_tokens=max(0,response.usage.prompt_tokens-cached-written),
                                  output_tokens=response.usage.completion_tokens,
                                  cache_read_input_tokens=cached,cache_creation_input_tokens=written)
        return SimpleNamespace(content=blocks,usage=usage,
                               request_id=getattr(response,'_request_id',None) or response.id,
                               stop_reason='max_tokens' if choice.finish_reason=='length' else 'end_turn')

    def _responses(self,model,system,messages,tools,max_tokens):
        inputs=[]
        def parts(content):
            if isinstance(content,str):return [{'type':'input_text','text':content}]
            result=[]
            for raw in content or []:
                p=_mapping(raw)
                if p.get('type')=='text':result.append({'type':'input_text','text':p['text']})
                elif p.get('type')=='image':
                    source=p['source']
                    result.append({'type':'input_image','image_url':'data:'+source['media_type']+';base64,'+source['data'],'detail':'original'})
            return result
        for message in messages:
            ordinary=[]
            content=message.get('content',[])
            if isinstance(content,str):
                inputs.append({'role':message['role'],'content':content});continue
            for raw in content:
                p=_mapping(raw)
                if p.get('type')=='tool_use':
                    inputs.append({'type':'function_call','call_id':p['id'],'name':p['name'],'arguments':json.dumps(p['input'],ensure_ascii=False)})
                elif p.get('type')=='tool_result':
                    value=p['content']
                    if isinstance(value,list) and any(_mapping(x).get('type')=='image' for x in value):
                        caption='\n'.join(_mapping(x).get('text','') for x in value if _mapping(x).get('type')=='text')
                        inputs.append({'type':'function_call_output','call_id':p['tool_use_id'],'output':'Página na mensagem seguinte. '+caption})
                        ordinary.extend(_mapping(x) for x in value)
                    else:
                        inputs.append({'type':'function_call_output','call_id':p['tool_use_id'],
                            'output':value if isinstance(value,str) else json.dumps(value,ensure_ascii=False)})
                else:ordinary.append(p)
            if ordinary:
                inputs.append({'role':message['role'],'content':parts(ordinary) if message['role']=='user' else '\n'.join(p.get('text','') for p in ordinary)})
        instructions=system if isinstance(system,str) else '\n'.join(_mapping(p).get('text','') for p in system)
        response=self.client.responses.create(model=model,instructions=instructions,input=inputs,
            max_output_tokens=max_tokens,reasoning={'effort':'medium'},service_tier='default',
            tools=[{'type':'function','name':t['name'],'description':t['description'],'parameters':t['input_schema'],'strict':False} for t in tools])
        blocks=[]
        for item in response.output:
            if item.type=='function_call':
                try:arguments=json.loads(item.arguments)
                except json.JSONDecodeError:arguments={'_invalid_json':item.arguments}
                blocks.append(SimpleNamespace(type='tool_use',name=item.name,input=arguments,id=item.call_id))
            elif item.type=='message':
                blocks.extend(SimpleNamespace(type='text',text=p.text) for p in item.content if p.type=='output_text')
        usage=None
        if response.usage:
            details=getattr(response.usage,'input_tokens_details',None)
            cached=int(getattr(details,'cached_tokens',0) or 0);written=int(getattr(details,'cache_creation_tokens',0) or 0)
            usage=SimpleNamespace(input_tokens=max(0,response.usage.input_tokens-cached-written),output_tokens=response.usage.output_tokens,
                cache_read_input_tokens=cached,cache_creation_input_tokens=written)
        return SimpleNamespace(content=blocks,usage=usage,request_id=getattr(response,'_request_id',None) or response.id,
            stop_reason='max_tokens' if response.status=='incomplete' else 'end_turn')


def client(family):
    if family=='B':
        return OpenAIAdapter()
    from anthropic import Anthropic
    return Anthropic(max_retries=0,timeout=600)
def _mapping(value):
    if isinstance(value,dict):
        return value
    if hasattr(value,'model_dump'):
        return value.model_dump()
    return vars(value)
