import os
import json
from time import sleep
from algosdk.v2client.algod import AlgodClient
from base64 import b64decode
from supabase import create_client
from get_docker_secret import get_docker_secret
from config import config
from algosdk import encoding


def get_application_address(app_id):
    to_sign = b"appID" + app_id.to_bytes(8, "big")
    checksum = encoding.checksum(to_sign)
    return encoding.encode_address(checksum)


SUPABASE_URL = get_docker_secret(os.environ.get('SUPABASE_URL'))
SUPABASE_KEY = get_docker_secret(os.environ.get('SUPABASE_KEY'))
CHAIN = os.environ.get('CHAIN', 'algo:testnet')
ENVIRONMENT = os.environ.get('ENVIRONMENT', 'dev')
FEES_APP_ID = config[CHAIN][ENVIRONMENT]
FEES_ADDRESS = get_application_address(FEES_APP_ID)
ALGOD_ADDRESS = os.environ.get('ALGOD_ADDRESS', 'http://localhost:4191')
ALGOD_TOKEN = os.environ.get('ALGOD_TOKEN', '')

client_supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

algod_client = AlgodClient(
    algod_token=ALGOD_TOKEN,
    algod_address=ALGOD_ADDRESS,
    headers={"X-Algo-API-Token": ALGOD_TOKEN},
)

note_authorized_param = {
    'auction': {
        'actions': ['create', 'bid', 'cancel', 'close'],
        'currency': ['1/72', '1/asa', 'asa/asa', '200/72']
    },
    'sale': {
        'actions': ['create', 'buy', 'cancel'],
        'currency': ['1/72', '1/asa', '1/rwa', 'asa/asa', 'asa/rwa', '200/72', '200/rwa']
    },
    'dutch': {
        'actions': ['create', 'buy', 'cancel'],
        'currency': ['1/72', '1/asa', 'asa/asa', '200/72']
    }
}

note_authorized = [
    f"{key},{action},{currency}"
    for key, params in note_authorized_param.items()
    for action in params['actions']
    for currency in params['currency']
]

def decode_note(transaction):
    try:
        inner_txns = [tx for tx in transaction['dt']['itx']
                      if 'note' in tx['txn'] and tx['txn']['type'] == 'pay' and tx['txn']['rcv'] == FEES_ADDRESS]
        return b64decode(inner_txns[0]['txn']['note']).decode('ascii')
    except:
        return None

def manager_round(round_num):
    print(round_num)
    block = algod_client.block_info(round_num)['block']
    if 'txns' not in block:
        return None
    # relevant_transactions = [txn for txn in block['txns']
    #                          if 'txn' in txn and 'apat' in txn['txn'] and FEES_ADDRESS in txn['txn']['apat']]
    relevant_transactions = [txn for txn in block['txns']
                             if FEES_ADDRESS in str(txn)]

    for transaction in relevant_transactions:
        print("find tx to fees address on this round")

        if 'txn' not in transaction:
            print("'txn' not in transaction")
            continue
        if 'apid' not in transaction['txn']:
            print("'apid' not in transaction['txn']")
            continue
        if 'snd' not in transaction['txn']:
            print("'snd' not in transaction['txn']")
            continue
        if 'grp' not in transaction['txn']:
            print("'grp' not in transaction['txn']")
            continue
        if 'dt' not in transaction:
            print("'dt' not in transaction")
            continue
        if 'itx' not in transaction['dt']:
            print("'itx' not in transaction['dt']")
            continue

        application_id = transaction['txn']['apid']
        group = transaction['txn']['grp']
        sender = transaction['txn']['snd']
        tx_id = group

        note = decode_note(transaction)
        if note not in note_authorized:
            print("note is not on proper format")
            continue
        action_tx = note.split(",")[1]
        currency_tx = note.split(",")[2].split("/")[0]
        price = None
        currency = None
        status = None
        if action_tx in ['cancel', 'create']:
            if action_tx == 'create':
                status = 'active'
            if action_tx == 'cancel':
                status = 'cancelled'

        if action_tx in ['close', 'buy']:
            status = 'closed'

            if currency_tx == '1':
                currency = 0
                price_1 = transaction['dt']['itx'][1]['txn']['amt'] if 'amt' in transaction['dt']['itx'][1]['txn'] else 0
                price_2 = transaction['dt']['itx'][3]['txn']['amt'] if 'amt' in transaction['dt']['itx'][3]['txn'] else 0
                price = price_1 + price_2

            if currency_tx == 'asa':
                currency = transaction['dt']['itx'][3]['txn']['xaid']
                price_1 = transaction['dt']['itx'][1]['txn']['aamt'] if 'aamt' in transaction['dt']['itx'][1]['txn'] else 0
                price_2 = transaction['dt']['itx'][3]['txn']['aamt'] if 'aamt' in transaction['dt']['itx'][3]['txn'] else 0
                price = price_1 + price_2

        if action_tx == 'bid':
            price = transaction['dt']['gd']['bid_amount']['ui']

        print({
            'id': tx_id,
            'from_address': sender,
            'chain': CHAIN,
            'app_id': application_id,
            'type': action_tx,
            'amount': price,
            'currency': currency,
            'note': note,
            'group_id': group
        })
        client_supabase.table('transactions').upsert({
            'id': tx_id,
            'from_address': sender,
            'chain': CHAIN,
            'app_id': application_id,
            'type': action_tx,
            'amount': price,
            'currency': currency,
            'note': note,
            'group_id': group
        }).execute()

        if status is not None:
            client_supabase.table('listings').update({'status': status}).eq('app_id', application_id).execute()


def start_indexer(check_round=None):
    if check_round is None:
        check_round = algod_client.status()['last-round'] - 2

    while True:
        current_round = algod_client.status()['last-round']
        while current_round - 2 < check_round:
            sleep(1)
            current_round = algod_client.status()['last-round']
        try:
            manager_round(check_round)
        except Exception as e:
            print("error", check_round, e)
        check_round += 1


if __name__ == "__main__":
    start_indexer()
