from algosdk.v2client.algod import AlgodClient
from algosdk.v2client.indexer import IndexerClient
from base64 import b64decode
from supabase import create_client
import os
from time import sleep


url = 'https://efxybjvydtmjzzsliimd.supabase.co'
key = os.environ['supabase_key']
client_supabase = create_client(url, key)
FEES_ADDRESS = 'LIEGRVYHMVOL6YHXXP6ZIX4EEUCHDCRQLUBWWTMMV6V77SS5C4AUMOWBSE'
chain = 'voi:testnet'

indexer_client = IndexerClient(
    indexer_token="",
    indexer_address="https://testnet-idx.voi.nodly.io",
    headers={"X-Algo-API-Token": ""}
)
algod_client = AlgodClient(
    algod_token="",
    algod_address="https://testnet-api.voi.nodly.io:443",
    headers={"X-Algo-API-Token": ""},
)

note_authorized_param = {
    'auction': {
        'actions': ['create', 'bid', 'cancel', 'close'],
        'currency': ['1/72', '1/asa', 'asa/asa', '200/72']
    },
    'sale': {
        'actions': ['create', 'buy', 'update', 'cancel'],
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


def decode_note(inner_txns):
    try:
        return b64decode(inner_txns[0]['note']).decode('ascii')
    except:
        return None


def manager_round(round_num):
    print(round_num)
    for transaction in indexer_client.search_transactions_by_address(FEES_ADDRESS, round_num=round_num)['transactions']:
        required_params = ['application-transaction', 'inner-txns', 'sender', 'id']
        if not all(param in transaction for param in required_params):
            continue
        if 'application-id' not in transaction['application-transaction']:
            continue
        application_id = transaction['application-transaction']['application-id']
        sender = transaction['sender']
        tx_id = transaction['id']
        group = transaction['group'] if 'group' in transaction else None
        inner_txns = [tx for tx in transaction['inner-txns']
                      if 'note' in tx and 'tx-type' in tx and tx['payment-transaction']['receiver'] == FEES_ADDRESS]
        if len(inner_txns) != 1:
            continue
        note = decode_note(inner_txns)
        if note not in note_authorized:
            continue
        action_tx = note.split(",")[1]
        currency_tx = note.split(",")[2].split("/")[0]
        price = None
        currency = None
        status = None
        if action_tx in ['update', 'cancel', 'create']:
            if action_tx == 'create':
                status = 'active'
            if action_tx == 'cancel':
                status = 'cancelled'

        if action_tx in ['close', 'buy']:
            status = 'closed'

            if currency_tx == '1':
                currency = 0
                price = transaction['inner-txns'][1]['payment-transaction']['amount'] + transaction['inner-txns'][3]['payment-transaction']['amount']

            if currency_tx == 'asa':
                currency = transaction['inner-txns'][1]['asset-transfer-transaction']['asset-id']
                price = transaction['inner-txns'][1]['asset-transfer-transaction']['amount'] + transaction['inner-txns'][3]['asset-transfer-transaction']['amount']

            if currency_tx == '200':
                currency = transaction['inner-txns'][1]['application-transaction']['application-id']
                price = int.from_bytes(
                    b64decode(
                        transaction['inner-txns'][1]['application-transaction']['application-args'][2]),
                    byteorder='big'
                ) + int.from_bytes(
                    b64decode(
                        transaction['inner-txns'][4]['application-transaction']['application-args'][2]),
                    byteorder='big'
                )

        if action_tx == 'bid':
            if currency_tx == '200':
                currency = transaction['application-transaction']['foreign-apps'][0]
            if currency_tx == '1' or currency_tx == '1':
                currency = 0
            if currency_tx == 'asa':
                currency = [element for element in indexer_client.applications(transaction['application-transaction']['application-id'])['application']['params']['global-state'] if element['key'] == 'cGFpbWVudF9hc2FfaWQ='][0]['value']['uint']
            price = [element for element in transaction['global-state-delta'] if b64decode(element['key']) == b'bid_amount'][0]['value']['uint']

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
        check_round = algod_client.status()['last-round']

    while True:
        current_round = algod_client.status()['last-round']
        while current_round < check_round:
            sleep(1)
            current_round = algod_client.status()['last-round']
        try:
            manager_round(check_round)
        except Exception as e:
            print("error", check_round, e)
        check_round += 1


if __name__ == "__main__":
    start_indexer()
