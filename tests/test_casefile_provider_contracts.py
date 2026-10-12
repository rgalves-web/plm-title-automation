"""Provider message and cost contracts without network calls."""
from types import SimpleNamespace as NS
from src.infra.providers import OpenAIAdapter
from src.casefile.worker import estimar_chamada


def test_long_context_reserves_higher_price_before_request():
    from src.infra.loop import RATES
    import json
    kw={'system':'x'*840000,'messages':[],'tools':[],'max_tokens':8000}
    tokens=len(json.dumps({k:kw[k] for k in ('system','messages','tools')},ensure_ascii=False))/3
    rate=RATES['gpt-5.6-terra']
    ordinary=(tokens*rate['input']+8000*rate['output'])/1_000_000
    assert estimar_chamada(kw,'gpt-5.6-terra')==2*ordinary


def test_tool_image_is_sent_as_user_image_after_text_tool_acknowledgement():
    captured={}
    def create(**kwargs):
        captured.update(kwargs)
        return NS(choices=[NS(message=NS(content='Synthetic reviewed page',tool_calls=[]),finish_reason='stop')],
                  usage=NS(prompt_tokens=10,completion_tokens=2,prompt_tokens_details=None),id='synthetic_response')
    sdk=NS(chat=NS(completions=NS(create=create)))
    messages=[{'role':'assistant','content':[{'type':'tool_use','id':'page_call','name':'read_page','input':{}}]},
              {'role':'user','content':[{'type':'tool_result','tool_use_id':'page_call','content':[
                  {'type':'image','source':{'type':'base64','media_type':'image/png','data':'synthetic_image_bytes'}},
                  {'type':'text','text':'sha256:synthetic page 1'}]}]}]
    response=OpenAIAdapter(sdk).create(model='gpt-5.6-terra',system='Synthetic blind test',messages=messages,tools=[],max_tokens=8000)
    assert [m['role'] for m in captured['messages']]==['system','assistant','tool','user']
    assert isinstance(captured['messages'][2]['content'],str)
    assert captured['messages'][3]['content'][0]['type']=='image_url'
    assert captured['messages'][3]['content'][1]['text']=='sha256:synthetic page 1'
    assert response.content[0].text=='Synthetic reviewed page'


def test_visual_estimate_uses_token_ceiling_and_not_base64_character_count():
    def request(data):
        return {'system':'Synthetic prompt','messages':[{'role':'user','content':[
            {'type':'image','source':{'type':'base64','media_type':'image/png','data':data}}]}],
            'tools':[],'max_tokens':8000}
    for model,maximum in [('claude-sonnet-5',.1),('gpt-5.6-terra',.2)]:
        small=estimar_chamada(request('x'),model)
        large=estimar_chamada(request('x'*3000000),model)
        assert large==small and 0<large<maximum


def test_responses_adapter_preserves_tool_call_ids_images_and_reasoning():
    captured={}
    def create(**kwargs):
        captured.update(kwargs)
        return NS(output=[NS(type='function_call',call_id='delivery_call',name='entregar_saida',arguments='{"saida":{"synthetic":true}}')],
            usage=NS(input_tokens=100,output_tokens=20,input_tokens_details=NS(cached_tokens=40)),
            id='synthetic_response',status='completed')
    adapter=OpenAIAdapter(NS(responses=NS(create=create)))
    result=adapter.create(model='gpt-5.6-terra',system='Independent synthetic reviewer',max_tokens=8000,
        tools=[{'name':'entregar_saida','description':'Synthetic output','input_schema':{'type':'object'}}],
        messages=[{'role':'assistant','content':[{'type':'tool_use','id':'page_call','name':'read_page','input':{'page':1}}]},
                  {'role':'user','content':[{'type':'tool_result','tool_use_id':'page_call','content':[
                      {'type':'image','source':{'type':'base64','media_type':'image/png','data':'synthetic'}},
                      {'type':'text','text':'Synthetic page reference'}]}]}])
    assert captured['reasoning']=={'effort':'medium'}
    assert captured['input'][0]['type']=='function_call' and captured['input'][0]['call_id']=='page_call'
    assert captured['input'][1]['type']=='function_call_output'
    assert captured['input'][2]['content'][0]['type']=='input_image'
    assert result.content[0].id=='delivery_call' and result.content[0].input=={'saida':{'synthetic':True}}
    assert result.usage.input_tokens==60 and result.usage.cache_read_input_tokens==40
