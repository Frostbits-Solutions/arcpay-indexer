from algosdk.v2client.algod import AlgodClient
from algosdk.v2client.indexer import IndexerClient
from base64 import b64decode
from supabase import create_client
import os
from time import sleep


url = ''
key = ''
client_supabase = create_client(url, key)
FEES_ADDRESS = 'UTOIVZJSC36XCL4HBVKHFYDA5WMBJQNR7GM3NPK5M7OH2SQBJW3KTUKZAA'
chain = 'algo:testnet'

algod_client = AlgodClient(
    algod_token="",
    algod_address="https://testnet-api.algonode.cloud",
    headers={"X-Algo-API-Token": ""},
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
    relevant_transactions = [txn for txn in block['txns']
                             if 'txn' in txn and 'apat' in txn['txn'] and FEES_ADDRESS in txn['txn']['apat']]

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
            'chain': chain,
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
            'chain': chain,
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
