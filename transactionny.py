#!/usr/bin/env python
# coding: utf-8

# In[1]:


import requests
import json
from typing import Dict, List, Optional, Union
import networkx as nx
import matplotlib.pyplot as plt

# Define a type for the API configuration
API_CONFIG = Dict[str, str]

class BlockchainAPIClient:
    """
    A client to interact with different Bitcoin blockchain explorers.
    Abstracts API calls to Blockchair, Blockchain.info, and Blockstream.
    """
    def __init__(self):
        self.api_endpoints = {
            "blockchair": {
                "base_url": "https://api.blockchair.com",
                "tx_endpoint": "/bitcoin/dashboards/transaction/{tx_hash}",
                "address_endpoint": "/bitcoin/dashboards/address/{address}",
                "recent_tx_endpoint": "/bitcoin/transactions" # For recent tx hashes
            },
            "blockchain.info": {
                "base_url": "https://blockchain.info",
                "tx_endpoint": "/rawtx/{tx_hash}",
                "address_endpoint": "/rawaddr/{address}"
                # blockchain.info's API for recent transactions is less direct for a list of hashes
                # We'll stick to blockchair for getting recent hashes for now if this is chosen.
            },
            "blockstream.info": {
                "base_url": "https://blockstream.info/api",
                "tx_endpoint": "/tx/{tx_hash}",
                "address_endpoint": "/address/{address}/txs" # Blockstream gives txs for address
            }
        }
        self.selected_api = None # Will be set by the user

    def set_api(self, api_name: str):
        """Sets the active API provider."""
        if api_name.lower() in self.api_endpoints:
            self.selected_api = api_name.lower()
            print(f"✅ API provider set to: {api_name.capitalize()}")
        else:
            raise ValueError(f"Unknown API provider: {api_name}. Choose from {list(self.api_endpoints.keys())}")

    def _make_request(self, url: str, params: Optional[Dict] = None) -> Optional[Dict]:
        """Helper to make API requests with proper error handling."""
        try:
            response = requests.get(url, params=params, timeout=15)
            response.raise_for_status()  # Raises HTTPError for bad responses (4xx or 5xx)
            return response.json()
        except requests.exceptions.HTTPError as e:
            if response.status_code == 404:
                print(f"❌ Error 404: Data not found for URL: {url}. This hash/address might not exist.")
            else:
                print(f"❌ HTTP Error for {url}: {e} (Status: {response.status_code})")
            return None
        except requests.exceptions.ConnectionError as e:
            print(f"❌ Connection Error for {url}: {e}. Check your internet connection or URL.")
            return None
        except requests.exceptions.Timeout as e:
            print(f"❌ Timeout Error for {url}: {e}. API took too long to respond.")
            return None
        except requests.exceptions.RequestException as e:
            print(f"❌ General Request Error for {url}: {e}")
            return None
        except json.JSONDecodeError as e:
            print(f"❌ Failed to parse JSON response from {url}: {e}")
            return None

    def get_transaction_data(self, tx_hash: str) -> Optional[Dict]:
        """Fetches and normalizes transaction data from the selected API."""
        if not self.selected_api:
            print("Error: API provider not selected. Call set_api() first.")
            return None

        print(f"🔍 Fetching transaction data for {tx_hash[:16]}... using {self.selected_api.capitalize()}")
        endpoint = self.api_endpoints[self.selected_api]["tx_endpoint"].format(tx_hash=tx_hash)
        url = f"{self.api_endpoints[self.selected_api]['base_url']}{endpoint}"
        data = self._make_request(url)

        if not data:
            return None

        # Normalize data based on API
        if self.selected_api == "blockchair":
            if 'data' in data and tx_hash in data['data']:
                tx_info = data['data'][tx_hash]['transaction']
                inputs = data['data'][tx_hash].get('inputs', [])
                outputs = data['data'][tx_hash].get('outputs', [])
                return {
                    'hash': tx_info['hash'],
                    'block_id': tx_info['block_id'],
                    'fees': tx_info['fee'],
                    'output_total': tx_info['output_total'],
                    'inputs': [{'recipient': inp['recipient'], 'value': inp['value'], 'prev_tx_hash': inp.get('spending_transaction_hash')} for inp in inputs],
                    'outputs': [{'recipient': out['recipient'], 'value': out['value'], 'is_spent': out['is_spent'], 'spending_tx_hash': out.get('spending_transaction_hash')} for out in outputs]
                }
        elif self.selected_api == "blockchain.info":
            # blockchain.info /rawtx has a simpler structure
            if 'hash' in data: # Check if the tx data is directly available
                inputs = [{'recipient': inp['prev_out']['addr'], 'value': inp['prev_out']['value']} for inp in data['inputs']]
                outputs = [{'recipient': out['addr'], 'value': out['value']} for out in data['out']]
                return {
                    'hash': data['hash'],
                    'block_id': data.get('block_height', 'N/A'),
                    'fees': data.get('fee', 'N/A'),
                    'output_total': sum(o['value'] for o in data['out']),
                    'inputs': inputs,
                    'outputs': outputs
                }
        elif self.selected_api == "blockstream.info":
            # Blockstream provides compact data for /tx/{tx_hash}
            if 'txid' in data:
                inputs = []
                for inp in data['vin']:
                    # Blockstream doesn't directly give sender address, need to fetch prev_out
                    # For simplicity here, we'll use a placeholder or previous txid
                    inputs.append({
                        'recipient': inp['prevout']['scriptpubkey_address'] if 'scriptpubkey_address' in inp['prevout'] else 'N/A (Blockstream needs prev_tx fetch)',
                        'value': inp['prevout']['value']
                    })
                outputs = []
                for out in data['vout']:
                    outputs.append({
                        'recipient': out['scriptpubkey_address'] if 'scriptpubkey_address' in out else 'N/A (script)',
                        'value': out['value'],
                        'is_spent': 'status' in out and out['status'].get('spent', False), # Blockstream provides spent status
                        'spending_tx_hash': out['status'].get('spent_txid') if out['status'].get('spent', False) else None
                    })
                return {
                    'hash': data['txid'],
                    'block_id': data['status']['block_height'] if data['status']['confirmed'] else 'Unconfirmed',
                    'fees': data.get('fee', 'N/A'),
                    'output_total': sum(o['value'] for o in data['vout']),
                    'inputs': inputs,
                    'outputs': outputs
                }

        print(f"❌ Failed to parse data from {self.selected_api.capitalize()} for transaction {tx_hash}.")
        return None

    def get_address_transactions(self, address: str) -> Optional[List[Dict]]:
        """Fetches and normalizes transaction list for an address."""
        if not self.selected_api:
            print("Error: API provider not selected. Call set_api() first.")
            return None

        print(f"🔍 Fetching transactions for address {address[:20]}... using {self.selected_api.capitalize()}")
        endpoint = self.api_endpoints[self.selected_api]["address_endpoint"].format(address=address)
        url = f"{self.api_endpoints[self.selected_api]['base_url']}{endpoint}"
        data = self._make_request(url)

        if not data:
            return None

        # Normalize data based on API
        transactions = []
        if self.selected_api == "blockchair":
            if 'data' in data and address in data['data'] and 'transactions' in data['data'][address]:
                transactions = data['data'][address]['transactions']
                # Blockchair provides a list of simplified tx objects for an address
                return [{'hash': tx['hash'], 'time': tx['time'], 'balance_change': tx['balance_change']} for tx in transactions]
        elif self.selected_api == "blockchain.info":
            # blockchain.info /rawaddr gives a list of txs directly
            if 'txs' in data:
                transactions = data['txs']
                # Need to iterate through inputs/outputs to determine balance_change for *this* address
                normalized_txs = []
                for tx in transactions:
                    balance_change = 0
                    for inp in tx.get('inputs', []):
                        if 'prev_out' in inp and inp['prev_out'].get('addr') == address:
                            balance_change -= inp['prev_out'].get('value', 0)
                    for out in tx.get('out', []):
                        if out.get('addr') == address:
                            balance_change += out.get('value', 0)
                    normalized_txs.append({
                        'hash': tx['hash'],
                        'time': tx.get('time', 'N/A'),
                        'balance_change': balance_change
                    })
                return normalized_txs
        elif self.selected_api == "blockstream.info":
            # Blockstream /address/{address}/txs gives a list of txs
            if isinstance(data, list): # Blockstream returns a list directly
                normalized_txs = []
                for tx in data:
                    # Blockstream doesn't provide balance_change directly for address within tx list
                    # You'd typically calculate this by parsing inputs/outputs or getting full tx data
                    # For simplicity, we'll just return the hash and timestamp.
                    normalized_txs.append({
                        'hash': tx['txid'],
                        'time': tx['status'].get('block_time', 'N/A') if tx['status'].get('confirmed', False) else 'Unconfirmed',
                        'balance_change': 'N/A (Requires full tx fetch)' # Placeholder
                    })
                return normalized_txs

        print(f"❌ Failed to parse address transaction data from {self.selected_api.capitalize()} for {address}.")
        return None

    def get_recent_transactions_hashes(self, limit=5) -> List[str]:
        """
        Fetches recent transaction hashes. Currently best supported by Blockchair.
        """
        if not self.selected_api:
            print("Error: API provider not selected. Call set_api() first.")
            return []

        print(f"🔍 Fetching {limit} recent transactions from {self.selected_api.capitalize()}...")
        if self.selected_api == "blockchair":
            endpoint = self.api_endpoints["blockchair"]["recent_tx_endpoint"]
            url = f"{self.api_endpoints['blockchair']['base_url']}{endpoint}?limit={limit}"
            data = self._make_request(url)

            if data and 'data' in data:
                return [tx['hash'] for tx in data['data'] if 'hash' in tx]
        elif self.selected_api == "blockchain.info":
            # blockchain.info's API for recent transactions is not a direct list of hashes.
            # It's more about unconfirmed transactions or specific blocks.
            print(f"⚠️ {self.selected_api.capitalize()} does not have a direct API endpoint for a simple list of recent transaction hashes like Blockchair. Please use Blockchair or enter a custom hash.")
            return []
        elif self.selected_api == "blockstream.info":
            # Blockstream has /blocks/tip/height and then /block/{hash}/txs
            # This would require two API calls and more parsing, outside the scope of a simple "recent list"
            print(f"⚠️ {self.selected_api.capitalize()} requires multiple calls (get block height, then get block transactions) to get a list of recent transactions. Please use Blockchair or enter a custom hash.")
            return []

        return []


class CryptocurrencyPrivacyAnalyzer:
    def __init__(self, api_client: BlockchainAPIClient):
        self.api_client = api_client
        self.transaction_graph = nx.DiGraph()
        self.address_clusters = {}

    def analyze_bitcoin_transaction(self, tx_hash: str):
        """Analyze a Bitcoin transaction and build address graph."""
        tx_data = self.api_client.get_transaction_data(tx_hash)

        if tx_data is None:
            print(f"❌ Could not retrieve or parse data for transaction {tx_hash}.")
            return None

        # Process transaction inputs and outputs
        inputs = tx_data.get('inputs', [])
        outputs = tx_data.get('outputs', [])

        print(f"\n📊 Transaction Analysis Results for {tx_data.get('hash', 'N/A')[:16]}...")
        print(f"   • Block ID: {tx_data.get('block_id', 'N/A')}")
        print(f"   • Inputs: {len(inputs)}")
        print(f"   • Outputs: {len(outputs)}")
        print(f"   • Total Output Value: {tx_data.get('output_total', 0) / 100000000:.8f} BTC")
        print(f"   • Fees: {tx_data.get('fees', 'N/A') / 100000000:.8f} BTC" if isinstance(tx_data.get('fees'), (int, float)) else f"   • Fees: {tx_data.get('fees', 'N/A')}")

        # Build transaction graph
        for inp in inputs:
            recipient = inp.get('recipient')
            if recipient and recipient != "nonstandard": # Filter out non-standard scripts without clear addresses
                self.transaction_graph.add_node(recipient, node_type='input')

        for out in outputs:
            recipient = out.get('recipient')
            if recipient and recipient != "nonstandard":
                self.transaction_graph.add_node(recipient, node_type='output')

        # Add edges between inputs and outputs
        for inp in inputs:
            in_recipient = inp.get('recipient')
            if in_recipient and in_recipient != "nonstandard":
                for out in outputs:
                    out_recipient = out.get('recipient')
                    if out_recipient and out_recipient != "nonstandard":
                        self.transaction_graph.add_edge(
                            in_recipient,
                            out_recipient,
                            tx_hash=tx_hash,
                            value=out.get('value', 0)
                        )
        return tx_data

    def get_address_transactions_info(self, address: str) -> List[Dict]:
        """Wrapper to get transactions from the API client."""
        transactions = self.api_client.get_address_transactions(address)
        if transactions is None:
            print(f"❌ Failed to get transactions for address {address}")
            return []
        print(f"✅ Found {len(transactions)} transactions for address {address[:20]}...")
        return transactions

    def cluster_addresses(self, addresses: List[str]):
        """Perform address clustering based on common spending patterns."""
        print("🔗 Performing address clustering analysis (simplified)...")
        # This is a highly simplified clustering. Real clustering is much more complex
        # and would involve heuristics like common input ownership.
        
        clusters = {}
        cluster_id = 0
        
        for address in addresses:
            if address not in self.address_clusters:
                # Simple clustering based on shared transactions in the graph
                # If two addresses are connected in the graph, they are part of the same cluster
                if address in self.transaction_graph:
                    component = list(nx.node_connected_component(self.transaction_graph.to_undirected(), address))
                    
                    # Only create a new cluster if this component hasn't been processed
                    new_cluster_found = False
                    for comp_addr in component:
                        if comp_addr in self.address_clusters:
                            # This address already belongs to an existing cluster, so merge/skip
                            new_cluster_found = False
                            break
                        new_cluster_found = True
                    
                    if new_cluster_found:
                        clusters[cluster_id] = component
                        for addr in component:
                            self.address_clusters[addr] = cluster_id
                        cluster_id += 1
                else:
                    # If address is not in graph, it's a single-node cluster
                    clusters[cluster_id] = [address]
                    self.address_clusters[address] = cluster_id
                    cluster_id += 1
        
        print(f"✅ Found {len(clusters)} clusters.")
        for cid, cluster_addrs in clusters.items():
            if len(cluster_addrs) > 1:
                print(f"   Cluster {cid}: {len(cluster_addrs)} addresses (e.g., {cluster_addrs[0][:8]}..., {cluster_addrs[1][:8]}...)")
            else:
                 print(f"   Cluster {cid}: {len(cluster_addrs)} address ({cluster_addrs[0][:8]}...)")
        
        return clusters

    def find_related_addresses(self, address: str) -> List[str]:
        """Find addresses that frequently appear in transactions with the given address."""
        related = []
        if address in self.transaction_graph:
            # Get neighbors (addresses involved in transactions with this address)
            neighbors = list(self.transaction_graph.neighbors(address))
            predecessors = list(self.transaction_graph.predecessors(address))
            related = neighbors + predecessors
        return list(set(related))

    def visualize_transaction_flow(self, tx_hash: str):
        """Visualize transaction flow."""
        print(f"📈 Creating visualization for transaction {tx_hash[:16]}...")

        if self.transaction_graph.number_of_nodes() == 0:
            print("❌ No transaction data to visualize. Please analyze a transaction first.")
            return

        plt.figure(figsize=(14, 10))
        # Use a consistent layout for better readability for small graphs
        pos = nx.spring_layout(self.transaction_graph, k=0.8, iterations=50)

        # Draw nodes
        input_nodes = [n for n, d in self.transaction_graph.nodes(data=True)
                       if d.get('node_type') == 'input']
        output_nodes = [n for n, d in self.transaction_graph.nodes(data=True)
                        if d.get('node_type') == 'output']

        # Nodes that are both input and output (change address back to sender)
        common_nodes = list(set(input_nodes) & set(output_nodes))
        input_only = list(set(input_nodes) - set(common_nodes))
        output_only = list(set(output_nodes) - set(common_nodes))

        nx.draw_networkx_nodes(self.transaction_graph, pos,
                               nodelist=input_only,
                               node_color='skyblue',  # Inputs
                               node_size=600,
                               alpha=0.8,
                               label='Inputs',
                               node_shape='s') # Square for inputs

        nx.draw_networkx_nodes(self.transaction_graph, pos,
                               nodelist=output_only,
                               node_color='lightgreen', # Outputs
                               node_size=600,
                               alpha=0.8,
                               label='Outputs',
                               node_shape='o') # Circle for outputs

        nx.draw_networkx_nodes(self.transaction_graph, pos,
                               nodelist=common_nodes,
                               node_color='gold', # Both input and output (change)
                               node_size=600,
                               alpha=0.8,
                               label='Change/Common',
                               node_shape='d') # Diamond for common

        # Draw edges
        nx.draw_networkx_edges(self.transaction_graph, pos,
                               edge_color='gray',
                               alpha=0.6,
                               arrows=True,
                               arrowsize=15,
                               width=1.5)

        # Add labels (truncated addresses)
        labels = {node: node[:8] + '...' for node in self.transaction_graph.nodes()}
        nx.draw_networkx_labels(self.transaction_graph, pos, labels, font_size=7, clip_on=False)

        # Add edge labels (values)
        edge_labels = nx.get_edge_attributes(self.transaction_graph, 'value')
        formatted_edge_labels = {
            (u, v): f"{val / 100000000:.4f} BTC" for u, v, val in self.transaction_graph.edges(data='value')
        }
        nx.draw_networkx_edge_labels(self.transaction_graph, pos, edge_labels=formatted_edge_labels, font_size=6, alpha=0.7)

        plt.title(f"Transaction Flow for {tx_hash[:16]}...", size=14)
        plt.legend(scatterpoints=1)
        plt.axis('off')
        plt.tight_layout()
        plt.show()

    def analyze_privacy_score(self, address: str) -> Dict:
        """Calculate privacy score for an address."""
        print(f"🔒 Calculating privacy score for {address[:20]}...")

        transactions = self.get_address_transactions_info(address)
        
        # Collect all unique addresses involved in these transactions to pass to clustering
        all_related_addresses_in_txs = set()
        for tx in transactions:
            tx_data = self.api_client.get_transaction_data(tx['hash']) # Re-fetch full tx data if needed
            if tx_data:
                for inp in tx_data.get('inputs', []):
                    if inp.get('recipient'):
                        all_related_addresses_in_txs.add(inp['recipient'])
                for out in tx_data.get('outputs', []):
                    if out.get('recipient'):
                        all_related_addresses_in_txs.add(out['recipient'])
        
        self.cluster_addresses(list(all_related_addresses_in_txs)) # Perform clustering on relevant addresses

        related_addresses = self.find_related_addresses(address)
        
        # Get the cluster ID for the analyzed address
        address_cluster_id = self.address_clusters.get(address)
        cluster_size = 0
        if address_cluster_id is not None:
            for cid, cluster_members in self.address_clusters.items():
                if cid == address_cluster_id:
                    cluster_size = len(cluster_members)
                    break


        # Simple privacy scoring heuristics
        privacy_score = {
            'transaction_count': len(transactions),
            'related_addresses_in_graph': len(related_addresses),
            'cluster_id': address_cluster_id,
            'cluster_size': cluster_size,
            'reused_addresses_risk': 'High' if len(related_addresses) > 5 else 'Low', # More than 5 related implies significant activity
            'privacy_rating': max(0, 100 - (cluster_size * 2 + len(related_addresses) * 3)) # Penalize larger clusters and more direct relations
        }

        print(f"\n🔒 Privacy Analysis Results for {address[:20]}...")
        print(f"   • Total Transactions: {privacy_score['transaction_count']}")
        print(f"   • Addresses Related in Graph: {privacy_score['related_addresses_in_graph']}")
        if privacy_score['cluster_id'] is not None:
            print(f"   • Identified Cluster ID: {privacy_score['cluster_id']}")
            print(f"   • Cluster Size (addresses in cluster): {privacy_score['cluster_size']}")
        else:
            print("   • Not yet part of a recognized cluster (only single address transactions processed)")
        print(f"   • Address Re-use/Linkability Risk: {privacy_score['reused_addresses_risk']}")
        print(f"   • Estimated Privacy Rating: {max(0, min(100, privacy_score['privacy_rating']))}/100 (Higher is better)")
        print("\nNote: This privacy score is a simplified heuristic. Real-world deanonymization is far more complex.")

        return privacy_score

def get_sample_data():
    """Returns sample transaction hashes and addresses."""
    sample_hashes = {
        "Genesis Block Transaction": "4a5e1e4baab89f3a32518a88c31bc87f618f76673e2cc77ab2127b7afdeda33b",
        "First Bitcoin Transaction": "f4184fc596403b9d638783cf57adfe4c75c605f6356fbc91338530e9831e9e16",
        "Bitcoin Pizza Day Transaction": "a1075db55d416d3ca199f55b6084e2115b9345e16c5cf302fc80e9d5fbf5d48d",
        "Large Value Transaction (Example)": "1dda35f8dc4e1b5f77acab2de77b78c4c62cb2def1e25bbcd28b7797ad69b43e",
        "Multi-input/output Transaction (Example)": "8c14f0db3df150123e6f3dbbf30f8b955a8249b62ac1d1ff16284aefa3d06d87"
    }

    sample_addresses = {
        "Satoshi Genesis Address": "1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa",
        "Binance Cold Wallet (Example)": "34xp4vRoCGJym3xR7yCVPFHoCNxv4Twseo",
        "BitMEX Cold Wallet (Example)": "3BMEXqGpG4qxBDfxBaE7eAyAJBwVRQ7m7",
        "FBI Silk Road Wallet (Example)": "1FfmbHfnpaZjKFvyi1okTjJJusN455paPH",
        "High Activity Address (Example)": "12ib7dApVFvg82TXKycWBNpN8kFyiAN1dr"
    }

    return sample_hashes, sample_addresses

def display_sample_data():
    """Display all available sample data."""
    sample_hashes, sample_addresses = get_sample_data()

    print("\n📚 SAMPLE BITCOIN TRANSACTION HASHES:")
    print("=" * 60)
    for i, (name, hash_val) in enumerate(sample_hashes.items(), 1):
        print(f"{i}. {name}")
        print(f"   Hash: {hash_val}")
        print()

    print("\n📚 SAMPLE BITCOIN ADDRESSES:")
    print("=" * 60)
    for i, (name, address) in enumerate(sample_addresses.items(), 1):
        print(f"{i}. {name}")
        print(f"   Address: {address}")
        print()

def interactive_hash_input(api_client: BlockchainAPIClient):
    """Interactive function to get transaction hash from user."""
    print("\n🔍 TRANSACTION HASH INPUT OPTIONS:")
    print("=" * 50)
    print("1. Enter your own transaction hash")
    print("2. Choose from sample transactions")
    print("3. Get recent transactions from blockchain (via Blockchair API)")
    print("4. Show usage guide")

    choice = input("\nEnter your choice (1-4): ").strip()

    if choice == "1":
        print("\n📝 Enter Custom Transaction Hash:")
        print("-" * 35)
        tx_hash = input("Paste Bitcoin transaction hash (64 characters): ").strip()

        if len(tx_hash) == 64 and all(c in '0123456789abcdefABCDEF' for c in tx_hash.lower()):
            # Test if the hash exists using the selected API
            print(f"Validating hash {tx_hash[:16]}... with {api_client.selected_api.capitalize()}")
            test_data = api_client.get_transaction_data(tx_hash)
            if test_data:
                print(f"✅ Transaction {tx_hash[:16]}... exists.")
                return tx_hash.lower()
            else:
                print(f"❌ Transaction {tx_hash} not found or accessible via {api_client.selected_api.capitalize()} API.")
                return None
        else:
            print("❌ Invalid hash format! Must be 64 hexadecimal characters.")
            print("Example: f4184fc596403b9d638783cf57adfe4c75c605f6356fbc91338530e9831e9e16")
            return None

    elif choice == "2":
        sample_hashes, _ = get_sample_data()
        print("\n📚 Choose from sample transactions:")
        print("-" * 40)

        hash_list = list(sample_hashes.items())
        for i, (name, _) in enumerate(hash_list, 1):
            print(f"{i}. {name}")

        try:
            selection = int(input(f"\nChoose (1-{len(hash_list)}): ")) - 1
            if 0 <= selection < len(hash_list):
                name, hash_val = hash_list[selection]
                print(f"\n✅ Selected: {name}")
                print(f"Hash: {hash_val}")
                return hash_val
            else:
                print("❌ Invalid selection")
                return None
        except ValueError:
            print("❌ Please enter a valid number")
            return None

    elif choice == "3":
        # Only Blockchair has a simple "recent transactions" endpoint for a list of hashes
        if api_client.selected_api != "blockchair":
            print(f"⚠️ 'Get recent transactions' is currently only supported via Blockchair API due to differences in other APIs. Please switch your API provider or select another option.")
            return None # Cannot proceed with this option if not Blockchair

        print("\n🌐 Fetching recent transactions from blockchain...")
        recent_hashes = api_client.get_recent_transactions_hashes(5)

        if recent_hashes:
            print(f"\n✅ Using most recent transaction: {recent_hashes[0]}")
            return recent_hashes[0]
        else:
            print("❌ Failed to fetch recent transactions from Blockchair API. Try again later or choose another input option.")
            return None

    elif choice == "4":
        print_usage_guide()
        return interactive_hash_input(api_client) # Recursive call to try again

    else:
        print("❌ Invalid choice. Please enter 1-4.")
        return None

def interactive_address_input(api_client: BlockchainAPIClient):
    """Interactive function to get Bitcoin address from user."""
    print("\n🏠 BITCOIN ADDRESS INPUT OPTIONS:")
    print("=" * 50)
    print("1. Enter your own Bitcoin address")
    print("2. Choose from sample addresses")

    choice = input("\nEnter your choice (1-2): ").strip()

    if choice == "1":
        address = input("Enter Bitcoin address: ").strip()
        # Basic validation for common Bitcoin address formats
        if address.startswith(('1', '3', 'bc1')) and 26 <= len(address) <= 64: # Increased max length for bc1
            # Test if the address exists using the selected API
            print(f"Validating address {address[:16]}... with {api_client.selected_api.capitalize()}")
            test_data = api_client.get_address_transactions(address)
            if test_data is not None: # Not None means API responded, even if tx list is empty
                print(f"✅ Address {address[:16]}... exists.")
                return address
            else:
                print(f"❌ Address {address} not found or accessible via {api_client.selected_api.capitalize()} API.")
                return None
        else:
            print("❌ Invalid Bitcoin address format.")
            print("Example: 1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa or bc1q...")
            return None

    elif choice == "2":
        _, sample_addresses = get_sample_data()
        print("\n📚 Choose from sample addresses:")
        print("-" * 40)

        addr_list = list(sample_addresses.items())
        for i, (name, _) in enumerate(addr_list, 1):
            print(f"{i}. {name}")

        try:
            selection = int(input(f"\nChoose (1-{len(addr_list)}): ")) - 1
            if 0 <= selection < len(addr_list):
                name, address = addr_list[selection]
                print(f"\n✅ Selected: {name}")
                print(f"Address: {address}")
                return address
            else:
                print("❌ Invalid selection")
                return None
        except ValueError:
            print("❌ Please enter a valid number")
            return None

    else:
        print("❌ Invalid choice. Please enter 1-2.")
        return None

def print_usage_guide():
    """Print comprehensive usage guide."""
    print("""
🚀 HOW TO GET BITCOIN TRANSACTION HASHES:
1. BLOCKCHAIN EXPLORERS (Recommended):
   • blockchain.com/explorer - Click any transaction
   • blockchair.com/bitcoin/transactions - Browse recent transactions
   • blockstream.info/tx - Search for a transaction
   • btc.com - Popular Bitcoin explorer
2. TRANSACTION HASH REQUIREMENTS:
   • Exactly 64 characters long
   • Contains only: 0-9, a-f (hexadecimal)
   • Example: f4184fc596403b9d638783cf57adfe4c75c605f6356fbc91338530e9831e9e16
3. BITCOIN ADDRESS REQUIREMENTS:
   • Starts with '1' (P2PKH), '3' (P2SH), or 'bc1' (Bech32/SegWit)
   • Length varies (e.g., 26-35 for legacy, longer for Bech32)
   • Example: 1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa or bc1q...
4. SAMPLE DATA:
   This tool provides famous Bitcoin transactions and addresses for testing.
5. API PROVIDER CHOICE:
   • Blockchair: Generally comprehensive and easy to use.
   • Blockchain.info: Historical and popular, but API can be tricky for detailed parsing.
   • Blockstream.info: Favored by many developers for direct access and focus on Bitcoin.
""")

def choose_api_provider(api_client: BlockchainAPIClient):
    """Allows the user to select the API provider."""
    print("\n🌐 SELECT API PROVIDER:")
    print("=" * 30)
    api_choices = list(api_client.api_endpoints.keys())
    for i, api in enumerate(api_choices, 1):
        print(f"{i}. {api.capitalize()}")
    
    while True:
        try:
            choice = int(input(f"\nEnter your choice (1-{len(api_choices)}): ").strip()) - 1
            if 0 <= choice < len(api_choices):
                api_client.set_api(api_choices[choice])
                break
            else:
                print("❌ Invalid selection. Please enter a number within the range.")
        except ValueError:
            print("❌ Invalid input. Please enter a number.")

def main():
    """Main interactive function."""
    print("🔍 CRYPTOCURRENCY PRIVACY ANALYZER")
    print("=" * 50)
    print("Analyze Bitcoin transactions and addresses for privacy insights")

    api_client = BlockchainAPIClient()
    choose_api_provider(api_client) # Allow user to choose API at the start

    analyzer = CryptocurrencyPrivacyAnalyzer(api_client)

    # --- Important Monero Privacy Note ---
    print("\n--- Monero Privacy Note ---")
    print("It's crucial to understand that Monero's design (Ring Signatures, Stealth Addresses, RingCT)")
    print("makes transaction tracing and deanonymization practically impossible with public APIs.")
    print("This tool is primarily for Bitcoin's pseudo-anonymous blockchain analysis.")
    print("-" * 50)


    while True:
        print("\n🎯 MAIN MENU:")
        print("-" * 20)
        print("1. Analyze Bitcoin Transaction (Trace Inputs/Outputs)")
        print("2. Analyze Bitcoin Address Privacy (Clustering & Risk)")
        print("3. Show Sample Data")
        print("4. Usage Guide")
        print("5. Change API Provider")
        print("6. Exit")

        choice = input("\nEnter your choice (1-6): ").strip()

        if choice == "1":
            print("\n🔍 BITCOIN TRANSACTION ANALYSIS")
            print("=" * 40)

            tx_hash = interactive_hash_input(api_client)
            if tx_hash:
                result = analyzer.analyze_bitcoin_transaction(tx_hash)

                if result:
                    # Check if the graph has nodes after analysis before visualizing
                    if analyzer.transaction_graph.number_of_nodes() > 0:
                        visualize = input("\n📈 Show transaction flow visualization? (y/n): ").lower()
                        if visualize == 'y':
                            analyzer.visualize_transaction_flow(tx_hash)
                    else:
                        print("ℹ️ No graph data was built for visualization (e.g., non-standard inputs/outputs).")
                else:
                    print("❌ Transaction analysis failed. Please try a different hash or API provider.")

        elif choice == "2":
            print("\n🔒 ADDRESS PRIVACY ANALYSIS")
            print("=" * 35)

            address = interactive_address_input(api_client)
            if address:
                analyzer.analyze_privacy_score(address)

        elif choice == "3":
            display_sample_data()

        elif choice == "4":
            print_usage_guide()
        
        elif choice == "5":
            choose_api_provider(api_client) # Allow changing API during runtime
            analyzer = CryptocurrencyPrivacyAnalyzer(api_client) # Re-initialize analyzer with new client

        elif choice == "6":
            print("\n👋 Thank you for using Cryptocurrency Privacy Analyzer!")
            print("Stay safe and keep your transactions private! 🔒")
            break

        else:
            print("❌ Invalid choice. Please enter 1-6.")

        input("\nPress Enter to continue...")

# Example of direct usage (for advanced users) - now needs API client
def quick_demo():
    """Quick demonstration with sample data."""
    print("🚀 QUICK DEMO - Using Sample Data (via Blockchair API by default)")
    print("=" * 40)

    api_client = BlockchainAPIClient()
    api_client.set_api("blockchair") # Default to Blockchair for demo

    analyzer = CryptocurrencyPrivacyAnalyzer(api_client)

    # Analyze famous first Bitcoin transaction
    print("\n1. Analyzing first Bitcoin transaction...")
    first_tx = "f4184fc596403b9d638783cf57adfe4c75c605f6356fbc91338530e9831e9e16"
    result = analyzer.analyze_bitcoin_transaction(first_tx)

    if result:
        print("\n2. Creating visualization...")
        analyzer.visualize_transaction_flow(first_tx)

        print("\n3. Analyzing Satoshi's address privacy...")
        satoshi_address = "1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa"
        analyzer.analyze_privacy_score(satoshi_address)

if __name__ == "__main__":
    print("Choose mode:")
    print("1. Interactive Mode (Recommended)")
    print("2. Quick Demo")

    mode = input("Enter choice (1-2): ").strip()

    if mode == "2":
        quick_demo()
    else:
        main()


# In[ ]:




