from algosdk.v2client.indexer import IndexerClient
from base64 import b64decode
from supabase import create_client
import os
from time import sleep


url = 'https://efxybjvydtmjzzsliimd.supabase.co'
key = os.environ['supabase_key']
client_supabase = create_client(url, key)
FEES_ADDRESS = '3FXLFER4JF4SPVBSSTPZWGTFUYSD54QOEZ4Y4TV4ZTRHERT2Z6DH7Q54YQ'
indexer_client = IndexerClient(
    indexer_token="",
    indexer_address="https://testnet-idx.voi.nodly.io",
    headers={"X-Algo-API-Token": ""}
)


def manager_round(round_num):
    chain = 'voi:testnet'
    for transaction in indexer_client.search_transactions_by_address(FEES_ADDRESS, round_num=round_num)['transactions']:
        if 'application-transaction' in transaction and 'inner-txns' in transaction:
            application_id = transaction['application-transaction']['application-id']
            app_args = transaction['application-transaction']['application-args']
            sender = transaction['sender']
            tx_id = transaction['id']
            group = transaction['group'] if 'group' in transaction else None
            inner_txns = [tx for tx in transaction['inner-txns']
                          if 'note' in tx and 'tx-type' in tx and tx['payment-transaction']['receiver'] == FEES_ADDRESS]
            if len(inner_txns) == 1:
                note = b64decode(inner_txns[0]['note']).decode('ascii')
                type_tx = note.split(",")[0]
                action_tx = note.split(",")[1]
                currency_tx = note.split(",")[2]
                price = None
                currency = None
                status = None
                if action_tx in ['update', 'cancel', 'create']:
                    if action_tx == 'create':
                        status = 'active'
                    if action_tx == 'cancel':
                        status = 'cancelled'
                    price = None
                    currency = None
                if action_tx == 'bid':
                    if currency_tx == '200/72':
                        currency = transaction['application-transaction']['foreign-apps'][0]
                        price = int.from_bytes(b64decode(app_args[1]), byteorder='big')
                    if currency_tx == '1/72':
                        currency = 1
                        price = [element for element in transaction['global-state-delta']
                                 if element['key'] == 'YmlkX2Ftb3VudA=='][0]['value']['uint']
                if action_tx == 'close':
                    status = 'closed'
                    if currency_tx == '1/72':
                        currency = 1
                        price = transaction['inner-txns'][2]['payment-transaction']['amount']
                    if currency_tx == '200/72':
                        currency = transaction['inner-txns'][3]['application-transaction']['application-id']
                        price = int.from_bytes(
                            b64decode(transaction['inner-txns'][3]['application-transaction']['application-args'][2]),
                            byteorder='big'
                        )
                if action_tx == 'buy':
                    status = 'closed'
                    if type_tx == 'sale':
                        if currency_tx == '1/72':
                            price = transaction['inner-txns'][1]['payment-transaction']['amount']
                            currency = 0
                        if currency_tx == '200/72':
                            currency = transaction['inner-txns'][2]['application-transaction']['application-id']
                            price = int.from_bytes(
                                b64decode(
                                    transaction['inner-txns'][2]['application-transaction']['application-args'][2]),
                                byteorder='big'
                            )
                        if currency_tx == '1/rwa':
                            price = transaction['inner-txns'][0]['payment-transaction']['amount']
                            currency = 0
                        if currency_tx == '200/rwa':
                            price = int.from_bytes(
                                b64decode(
                                    transaction['inner-txns'][1]['application-transaction']['application-args'][2]),
                                byteorder='big'
                            )
                            currency = transaction['inner-txns'][1]['application-transaction']['application-id']
                    if type_tx == 'dutch':
                        if currency_tx == '1/72':
                            price = transaction['inner-txns'][0]['payment-transaction']['amount']
                            currency = 0
                        if currency_tx == '200/72':
                            price = int.from_bytes(b64decode(app_args[1]), byteorder='big')
                            currency = transaction['inner-txns'][1]['application-transaction']['application-id']

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
        check_round = indexer_client.search_transactions_by_address(FEES_ADDRESS, round_num=0)['current-round']

    while True:
        current_round = indexer_client.search_transactions_by_address(FEES_ADDRESS, round_num=check_round)[
            'current-round']
        while current_round < check_round:
            sleep(1)
            current_round = indexer_client.search_transactions_by_address(FEES_ADDRESS, round_num=check_round)[
                'current-round']
        try:
            manager_round(check_round)
        except:
            print("error", check_round)
        check_round += 1


if __name__ == "__main__":
    start_indexer()
