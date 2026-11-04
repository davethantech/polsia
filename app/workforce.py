"""Explicit tool-capability inventory, not fictional autonomous agents."""
import os
from . import providers, business


def catalog():
    local = providers.configuration()
    model_ready = bool(local.get('live_requests'))
    network = os.environ.get('POLSIA_NETWORK_ENABLED') == '1'
    basic={'execution_engine':'persistent_mission_dag', 'model':local,
      'agents':[
        {'id':'software_inspector','role':'QA / static inspector','tool':'software.inspect',
         'available':True,'mode':'deterministic','limitations':'Python/JSON syntax checks only; no runtime tests'},
        {'id':'software_engineer','role':'Software engineer / patch proposer','tool':'software.propose',
         'available':model_ready,'mode':'local_language_model',
         'limitations':'Creates reviewable files; no execution, Git push, PR or deployment'},
        {'id':'researcher','role':'Bounded web researcher','tool':'research.fetch',
         'available':network,'mode':'authorized_https_fetch',
         'limitations':'Only a supplied public URL; no unrestricted web search'},
        {'id':'mathematician','role':'Verified arithmetic','tool':'math.evaluate',
         'available':True,'mode':'deterministic',
         'limitations':'Bounded expression evaluation, not mathematical research'},
        {'id':'knowledge_curator','role':'Company memory curator','tool':'knowledge.store',
         'available':True,'mode':'deterministic',
         'limitations':'Persists labeled inputs; does not independently establish truth'},
      ],
      'unimplemented_roles':['autonomous_CEO','sales_operator','marketing_publisher',
                             'deployment_operator','finance_transaction_agent'],
      'agent_count_claim':'only listed capabilities are implemented; these are roles, not separate neural models'}
    basic['agents'].extend({'id':'business_'+role,'role':title+' / business draft',
      'tool':'business.draft','available':model_ready,'mode':'local_language_model',
      'limitations':'Produces a persisted unverified business draft; does not perform third-party actions'}
      for role,(title,_) in business.ROLES.items())
    basic['business_execution']=business.capabilities()
    return basic
