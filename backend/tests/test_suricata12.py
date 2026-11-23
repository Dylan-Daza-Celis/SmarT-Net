"""Iteration12: synthetic examples, isolated databases, no live sensor or user data."""
import hashlib
import json
import os
from pathlib import Path
import secrets
import sys
from uuid import uuid4
import pytest
from pydantic import ValidationError
from sqlalchemy import select, text
import yaml

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'agent'))
from app.suricata import adapt_line, FINGERPRINT_VERSION
from app.suricata_policy import LAB_SIGNATURE, LAB_EVENT_TYPE
from app import ingestion, risk
from app.models import User, Event, Incident
from app.evaluation_data import synthetic, FeatureCase
from smartir_agent.config import Config
from smartir_agent.store import Store
from smartir_agent.tailer import Tailer
from smartir_agent.runner import Agent
from smartir_agent.transport import Transport
from tools.suricata_alerts_config import create, verify, ConfigError
from validation.synthetic_icmp import make_pcap, checksum


def example(index=0, **alert_fields):
    return {'timestamp':f'2026-01-01T00:01:0{index}.123456+0000','event_type':'alert',
            'src_ip':'192.0.2.10','dest_ip':'198.51.100.20','proto':'ICMP','icmp_type':8,'icmp_code':0,
            'alert':{'signature':LAB_SIGNATURE,'signature_id':9900012,'category':'','severity':3,**alert_fields},
            'synthetic':True}


def raw(item):return json.dumps(item,separators=(',',':')).encode()
def adapt(item):return adapt_line(raw(item),sensor_id='lab12',filename='synthetic.jsonl',import_id=str(uuid4()),line_number=1)
def meta(record):return json.loads(record.attributes['adapter_metadata'])


@pytest.mark.parametrize('value,index,level',[(None,50,None),(0,100,None),(1,100,'Crítica'),(2,70,'Alta'),
                                           (3,40,'Media'),(4,10,'Baja'),(255,10,'Baja')])
def test_explicit_criticality_policy_keeps_asset_independent(value,index,level):
    item=example(severity=value)
    record=adapt(item);m=meta(record);c=m['alert_criticality']
    assert record.event.severity==index==c['value'] and c['level']==level
    assert m['suricata_severity']==value and c['source_value']==value and c['observed'] is False
    assert c['source_provided']==(value is not None) and c['standard_priority']==(value is not None and value>0)
    assert record.event.asset_criticality==50 and 'asset_criticality' not in record.event.model_fields_set
    assert m['asset_criticality']=={'value':50,'observed':False,'policy':'unknown_default_50'}
    assert json.loads(record.raw_event)['alert']['severity']==value


@pytest.mark.parametrize('category',['',None,'   ','MISSING'])
def test_empty_categories_match_only_explicit_declared_icmp(category):
    item=example(category=category)
    if category=='MISSING':item['alert'].pop('category')
    record=adapt(item);m=meta(record)
    assert record.event.event_type==LAB_EVENT_TYPE and m['classification']['taxonomy']=='auxiliary_non_attack'
    assert record.event.message==LAB_SIGNATURE and m['signature_id']==9900012
    assert m['category_status']==('missing' if category=='MISSING' else 'null' if category is None else 'empty')
    assert m['original_timestamp']==item['timestamp'] and record.event.event_timestamp.isoformat()=='2026-01-01T00:01:00.123456+00:00'
    assert record.event.source_ip==item['src_ip'] and record.event.destination_ip==item['dest_ip']
    assert record.raw_event==raw(item).decode() and record.evidence['raw_sha256']==hashlib.sha256(raw(item)).hexdigest()


@pytest.mark.parametrize('protocol',['ICMP','IPv6-ICMP','ICMPv6'])
def test_declared_icmp_protocols_and_ipv6_canonicalization(protocol):
    item=example();item.update(proto=protocol,src_ip='2001:0db8::1',dest_ip='2001:db8::2')
    record=adapt(item)
    assert record.event.event_type==LAB_EVENT_TYPE and record.event.source_ip=='2001:db8::1'
    assert meta(record)['protocol']==protocol and '2001:0db8::1' in record.raw_event


@pytest.mark.parametrize('changes',[{'signature':'Prefix '+LAB_SIGNATURE},{'signature':LAB_SIGNATURE+' suffix'},
                                  {'category':'Unmapped category'},{'signature':None}])
def test_no_attack_inferred_from_unknown_category_or_substrings(changes):
    record=adapt(example(**changes));m=meta(record)
    assert record.event.event_type=='desconocido' and m['classification']['matched'] is False and m['classification']['reason']
    assert m['alert_criticality']['value']==40


@pytest.mark.parametrize('protocol',['TCP',None])
def test_signature_does_not_impute_missing_or_wrong_protocol(protocol):
    item=example();item['proto']=protocol
    assert adapt(item).event.event_type=='desconocido'


def test_category_taxonomy_precedes_lab_and_ml_taxonomy_stays_six():
    assert adapt(example(category='A Network Trojan was detected')).event.event_type=='malware'
    item=synthetic(count=6).cases[0].model_dump(mode='json');item['event_type']=LAB_EVENT_TYPE
    with pytest.raises(ValidationError):FeatureCase.model_validate(item)


def test_fingerprint_namespace_original_fields_and_provenance_are_unchanged():
    item=example();r=adapt(item)
    previous=hashlib.sha256(json.dumps([FINGERPRINT_VERSION,'lab12',item],sort_keys=True,ensure_ascii=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
    assert r.fingerprint==previous and FINGERPRINT_VERSION=='suricata-eve-fp-v1'
    assert adapt_line(b'\xef\xbb\xbf'+json.dumps(item,sort_keys=True).encode(),sensor_id='lab12',filename='other',import_id='other',line_number=1).fingerprint==previous
    assert adapt(example(signature_id=9900013)).fingerprint!=previous
    assert adapt_line(raw(item),sensor_id='other',filename='other',import_id='other',line_number=1).fingerprint!=previous


def upload(c,h,body):return c.post('/api/events/import/eve?sensor_id=lab12&filename=synthetic.jsonl',content=body,
                                 headers={**h,'Content-Type':'application/x-ndjson'})


def test_four_new_alerts_one_incident_and_duplicate_evidence(api,headers):
    c,s,_=api;h=headers('analista');body=b'\n'.join(raw(example(i)) for i in range(4))+b'\n'
    report=upload(c,h,body).json();assert report['imported']==4 and report['unknown']==0
    incident=c.get('/api/incidents',headers=h).json()[0]
    assert incident['event_type']==LAB_EVENT_TYPE and incident['event_count']==4
    assert incident['score']==50  # unchanged generic weighted-v2: 14+12.5+12+6+5=49.5 -> 50
    frozen=c.get('/api/incidents/'+incident['id']+'/evaluations',headers=h).json()
    again=upload(c,h,body).json();assert (again['imported'],again['duplicates'])==(0,4)
    assert c.get('/api/incidents/'+incident['id']+'/evaluations',headers=h).json()==frozen
    detail=c.get('/api/incidents/'+incident['id'],headers=h).json()
    for e in detail['events']:
        assert e['severity']==40 and e['asset_criticality']==50 and e['asset_criticality_observed'] is False
        evidence=c.get('/api/events/'+e['id']+'/evidence',headers=h).json();assert len(evidence)==2
        assert e['adapter_metadata']['alert_criticality']['observed'] is False
    filtered=c.get('/api/analytics/dashboard',params={'start':'2026-01-01T00:00:00Z','end':'2026-01-02T00:00:00Z',
        'time_basis':'event_timestamp','event_type':LAB_EVENT_TYPE},headers=headers('observador')).json()
    assert filtered['totals']['incidents']==1 and filtered['totals']['events']==4


@pytest.mark.parametrize('version',['weighted-v1','weighted-v2'])
def test_old_events_parameters_metadata_and_frozen_risks_never_rewritten(api,headers,monkeypatch,version):
    c,s,_=api;h=headers('analista')
    with s() as db:uid=db.scalar(select(User.id).where(User.role=='analista'))
    original_params={**risk.parameters(),'algorithm_version':version}
    monkeypatch.setattr(ingestion,'parameters',lambda:original_params)
    records=[]
    for i in range(4):
        r=adapt(example(i));r.event=r.event.model_copy(update={'event_type':'desconocido'})
        r.attributes={'adapter_metadata':json.dumps({'adapter_version':'suricata-eve-v1','suricata_severity':3,
            'signature':LAB_SIGNATURE,'signature_id':9900012,'category':'','asset_criticality':{'value':50,'observed':False,'policy':'unknown_default_50'}})}
        records.append(r)
    ingestion.ingest(records,uid,s,eve_service=True)
    initial=c.get('/api/incidents',headers=h).json()[0];path='/api/incidents/'+initial['id']
    detail=c.get(path,headers=h).json();frozen=c.get(path+'/evaluations',headers=h).json()
    with s() as db:params=db.get(Incident,initial['id']).risk_parameters
    result=upload(c,h,b'\n'.join(raw(example(i)) for i in range(4))).json()
    assert (result['imported'],result['duplicates'])==(0,4)
    assert len(c.get('/api/incidents',headers=h).json())==1
    assert c.get(path,headers=h).json()==detail and c.get(path+'/evaluations',headers=h).json()==frozen
    with s() as db:assert db.get(Incident,initial['id']).risk_parameters==params
    assert initial['event_type']=='desconocido' and all(e['adapter_metadata']['adapter_version']=='suricata-eve-v1' for e in detail['events'])


def test_agent_existing_checkpoint_and_pending_receipt_compatibility(api,headers,tmp_path):
    c,s,_=api;password=secrets.token_urlsafe(24)
    assert c.post('/api/users',headers=headers('administrador'),json={'username':'iter12-agent','password':password,'role':'analista','eve_only':True}).status_code==201
    source=tmp_path/'eve.json';source.write_bytes(b'\n'.join(raw(example(i)) for i in range(4))+b'\n')
    cfg=Config(source=source,state_dir=tmp_path/'state',api_url='http://localhost',sensor_id='lab12')
    store=Store(cfg);pending=Tailer(store).poll();binding=store.get('binding');store.close()
    store=Store(cfg)
    try:
        assert store.get('binding')==binding and store.pending()['sha256']==pending['sha256'] and store.pending()['id']==pending['id']
        transport=Transport(cfg,client=c,credential_provider=lambda:('iter12-agent',password))
        Agent(store,transport).step()
        assert store.pending() is None and store.source()['offset']==source.stat().st_size
        assert json.loads(store.db.execute('SELECT report FROM batches').fetchone()[0])['imported']==4
        with s() as db:assert all(e.event_type==LAB_EVENT_TYPE for e in db.scalars(select(Event)))
    finally:store.close()


def base(tmp_path):
    p=tmp_path/'base.yaml';p.write_text((ROOT/'config/suricata/lab-base.yaml').read_text(encoding='utf-8'),encoding='utf-8');return p


def test_wrapper_preserves_base_and_all_original_outputs(tmp_path):
    source=base(tmp_path);before=source.read_bytes();target=tmp_path/'generated.yaml'
    result=create(source,target,'/mnt/c/SmartIRLab/smartir-alerts.json')
    loaded=yaml.safe_load(target.read_text(encoding='utf-8'))
    assert loaded['include']==str(source.resolve()) and source.read_bytes()==before
    assert loaded['outputs'][:-1]==yaml.safe_load(before)['outputs']
    new=loaded['outputs'][-1]['eve-log']
    assert new['types']==['alert'] and new['threaded'] is False and new['buffer-size']==0
    assert new['filetype']=='regular' and result['added_outputs']==1 and verify(target)['base_unchanged']
    with pytest.raises(FileExistsError):create(source,target)
    assert source.read_bytes()==before
    if os.name!='nt':assert target.stat().st_mode&0o077==0
    source.write_bytes(before+b'\n# changed\n')
    with pytest.raises(ConfigError,match='base_changed'):verify(target)


@pytest.mark.parametrize('mode',['same_file','collision','include','duplicate','flow_list'])
def test_unsafe_or_ambiguous_config_rejected_without_overwrite(tmp_path,mode):
    source=base(tmp_path);target=tmp_path/'generated.yaml';eve_file='smartir-alerts.json'
    if mode=='same_file':target=source
    if mode=='collision':eve_file='eve-general.json'
    if mode=='include':source.write_text(source.read_text()+'\ninclude: private-other.yaml\n')
    if mode=='duplicate':source.write_text(source.read_text()+'\noutputs: []\n')
    if mode=='flow_list':source.write_text('outputs: []\n')
    before=source.read_bytes()
    with pytest.raises(ConfigError):create(source,target,eve_file)
    assert source.read_bytes()==before
    if target!=source:assert not target.exists()


def test_wrapper_check_rejects_locally_changed_logger(tmp_path):
    source=base(tmp_path);target=tmp_path/'generated.yaml';create(source,target)
    text=target.read_text(encoding='utf-8').replace('    - alert\n','    - flow\n')
    target.write_text(text,encoding='utf-8')
    with pytest.raises(ConfigError):verify(target)


def test_pcap_generator_is_deterministic_and_checksums_valid():
    import struct
    packet=make_pcap();assert packet==make_pcap();cursor=24;count=0
    while cursor<len(packet):
        sec,micro,size,original=struct.unpack('<IIII',packet[cursor:cursor+16]);cursor+=16
        frame=packet[cursor:cursor+size];cursor+=size;count+=1
        assert size==original and checksum(frame[14:34])==0 and checksum(frame[34:])==0
        assert b'SYNTHETIC OFFLINE PCAP ONLY' in frame
    assert count==4
