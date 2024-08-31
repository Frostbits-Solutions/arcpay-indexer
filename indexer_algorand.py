from algosdk.v2client.indexer import IndexerClient
from base64 import b64decode
from supabase import create_client
import os
from time import sleep


url = 'https://efxybjvydtmjzzsliimd.supabase.co'
key = os.environ['supabase_key']

client_supabase = create_client(url, key)
FEES_ADDRESS = 'UTOIVZJSC36XCL4HBVKHFYDA5WMBJQNR7GM3NPK5M7OH2SQBJW3KTUKZAA'


algod_token_tx = ""
headers_tx = {"X-Algo-API-Token": algod_token_tx}
indexer_client = IndexerClient(
    indexer_token="",
    indexer_address="https://testnet-idx.algonode.cloud",
    headers={"X-Algo-API-Token": ""}
)


def manager_round(round_num):
    chain = 'algo:testnet'
    for transaction in indexer_client.search_transactions_by_address(FEES_ADDRESS, round_num=round_num)['transactions']:
        if 'application-transaction' in transaction and 'inner-txns' in transaction:
            application_id = transaction['application-transaction']['application-id']
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
                    if currency_tx == 'asa/asa':
                        currency = [element for element in indexer_client.applications(transaction['application-transaction']['application-id'])['application']['params']['global-state'] if element['key'] == 'cGFpbWVudF9hc2FfaWQ='][0]['value']['uint']
                        price = [element for element in transaction['global-state-delta'] if element['key'] == 'YmlkX2Ftb3VudA=='][0]['value']['uint']
                    if currency_tx == '1/asa':
                        currency = 1
                        price = [element for element in transaction['global-state-delta'] if element['key'] == 'YmlkX2Ftb3VudA=='][0]['value']['uint']

                if action_tx == 'close':
                    status = 'closed'
                    if currency_tx == '1/asa':
                        currency = 1
                        price = transaction['inner-txns'][1]['payment-transaction']['amount'] + transaction['inner-txns'][3]['payment-transaction']['amount']
                    if currency_tx == 'asa/asa':
                        currency = transaction['inner-txns'][1]['asset-transfer-transaction']['asset-id']
                        price = transaction['inner-txns'][1]['asset-transfer-transaction']['amount'] + transaction['inner-txns'][3]['asset-transfer-transaction']['amount']

                if action_tx == 'buy':
                    status = 'closed'
                    if type_tx == 'sale':
                        if currency_tx == 'asa/rwa':
                            price = transaction['inner-txns'][1]['asset-transfer-transaction']['amount'] + transaction['inner-txns'][3]['asset-transfer-transaction']['amount']
                            currency = transaction['inner-txns'][3]['asset-transfer-transaction']['asset-id']
                        if currency_tx == '1/asa':
                            price = transaction['inner-txns'][1]['payment-transaction']['amount'] + transaction['inner-txns'][3]['payment-transaction']['amount']
                            currency = 0
                        if currency_tx == 'asa/asa':
                            price = transaction['inner-txns'][1]['asset-transfer-transaction']['amount'] + transaction['inner-txns'][3]['asset-transfer-transaction']['amount']
                            currency = transaction['inner-txns'][1]['asset-transfer-transaction']['asset-id']
                        if currency_tx == '1/rwa':
                            price = transaction['inner-txns'][1]['payment-transaction']['amount'] + transaction['inner-txns'][3]['payment-transaction']['amount']
                            currency = 0

                    if type_tx == 'dutch':
                        if currency_tx == '1/asa':
                            price = transaction['inner-txns'][1]['payment-transaction']['amount'] + transaction['inner-txns'][3]['payment-transaction']['amount']
                            currency = 0
                        if currency_tx == 'asa/asa':
                            price = transaction['inner-txns'][1]['asset-transfer-transaction']['amount'] + transaction['inner-txns'][3]['asset-transfer-transaction']['amount']
                            currency = transaction['inner-txns'][1]['asset-transfer-transaction']['asset-id']

                # print({
                #     'id': tx_id,
                #     'from_address': sender,
                #     'chain': chain,
                #     'app_id': application_id,
                #     'type': action_tx,
                #     'amount': price,
                #     'currency': currency,
                #     'note': note,
                #     'group_id': group
                # })
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
    start_indexer(None)
