#!/usr/bin/env python
# coding: utf-8

# In[ ]:


import requests
import json
import time
import csv
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timezone

class BlockchainAPIClient:
    def __init__(self):
        self.selected_api = "blockstream"
        self.base_urls = {
            "blockstream": "https://blockstream.info/api",
            "blockchair": "https://api.blockchair.com/bitcoin"
        }
        self.rate_limit_delay = 1  # seconds between requests
        
    def get_base_url(self):
        return self.base_urls[self.selected_api]
    
    def make_request(self, url: str, max_retries: int = 3) -> Optional[Dict]:
        """Make HTTP request with error handling and retries"""
        for attempt in range(max_retries):
            try:
                time.sleep(self.rate_limit_delay)
                response = requests.get(url, timeout=30)
                
                if response.status_code == 200:
                    return response.json()
                elif response.status_code == 429:
                    print(f"⚠️ Rate limited. Waiting {(attempt + 1) * 2} seconds...")
                    time.sleep((attempt + 1) * 2)
                    continue
                else:
                    print(f"❌ HTTP {response.status_code} for {url}")
                    return None
                    
            except requests.exceptions.RequestException as e:
                print(f"❌ Request failed (attempt {attempt + 1}/{max_retries}): {e}")
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)
                    
        return None
    
    def validate_address(self, address: str) -> bool:
        """Validate Bitcoin address by checking if it exists on the blockchain"""
        print(f"Validating address {address[:12]}... with {self.selected_api.title()}")
        
        url = f"{self.get_base_url()}/address/{address}"
        data = self.make_request(url)
        
        if data is not None:
            print(f"✅ Address {address[:12]}... exists.")
            return True
        else:
            print(f"❌ Address {address[:12]}... not found or invalid.")
            return False
    
    def get_address_transactions(self, address: str, limit: int = 50) -> List[Dict]:
        """Get transaction history for an address"""
        print(f"🔍 Fetching transactions for address {address[:20]}... using {self.selected_api.title()}")
        
        url = f"{self.get_base_url()}/address/{address}/txs"
        data = self.make_request(url)
        
        if data is None:
            print(f"❌ Failed to fetch transactions for {address[:12]}...")
            return []
        
        transactions = []
        for tx in data[:limit]:  # Limit transactions processed
            try:
                transactions.append({
                    'hash': tx['txid'],
                    'block_height': tx['status'].get('block_height') if tx['status'].get('confirmed', False) else None,
                    'timestamp': tx['status'].get('block_time') if tx['status'].get('confirmed', False) else None,
                    'fee': tx.get('fee', 0),
                    'size': tx.get('size', 0),
                    'weight': tx.get('weight', 0),
                    'input_count': len(tx.get('vin', [])),
                    'output_count': len(tx.get('vout', [])),
                    'confirmed': tx['status'].get('confirmed', False)
                })
            except (KeyError, TypeError) as e:
                print(f"⚠️ Skipping malformed transaction: {e}")
                continue
        
        print(f"✅ Found {len(transactions)} transactions for address {address[:20]}...")
        return transactions
    
    def get_transaction_data(self, tx_hash: str) -> Optional[Dict]:
        """Get detailed transaction data"""
        print(f"🔍 Fetching transaction data for {tx_hash[:16]}... using {self.selected_api.title()}")
        
        url = f"{self.get_base_url()}/tx/{tx_hash}"
        data = self.make_request(url)
        
        if data is None:
            print(f"❌ Failed to fetch transaction data for {tx_hash[:16]}...")
            return None
        
        try:
            # Parse inputs
            inputs = []
            for inp in data.get('vin', []):
                prev_out = inp.get('prevout', {})
                inputs.append({
                    'sender': prev_out.get('scriptpubkey_address', 'N/A (script)'),
                    'value': prev_out.get('value', 0),
                    'prev_tx_hash': inp.get('txid'),
                    'prev_tx_index': inp.get('vout'),
                    'script_type': prev_out.get('scriptpubkey_type', 'unknown')
                })
            
            # Parse outputs
            outputs = []
            for out in data.get('vout', []):
                # Safely handle status field
                status = out.get('status', {})
                is_spent = status.get('spent', False) if isinstance(status, dict) else False
                spending_tx_hash = status.get('spent_txid') if is_spent else None
                
                outputs.append({
                    'recipient': out.get('scriptpubkey_address', 'N/A (script)'),
                    'value': out.get('value', 0),
                    'is_spent': is_spent,
                    'spending_tx_hash': spending_tx_hash,
                    'script_type': out.get('scriptpubkey_type', 'unknown')
                })
            
            return {
                'hash': data['txid'],
                'block_id': data['status'].get('block_height') if data['status'].get('confirmed', False) else 'Unconfirmed',
                'timestamp': data['status'].get('block_time') if data['status'].get('confirmed', False) else None,
                'fee': data.get('fee', 0),
                'size': data.get('size', 0),
                'weight': data.get('weight', 0),
                'inputs': inputs,
                'outputs': outputs,
                'confirmed': data['status'].get('confirmed', False)
            }
            
        except (KeyError, TypeError) as e:
            print(f"❌ Failed to parse transaction data for {tx_hash[:16]}...: {e}")
            return None

class CryptocurrencyPrivacyAnalyzer:
    def __init__(self, api_client: BlockchainAPIClient):
        self.api_client = api_client
        
    def calculate_privacy_score(self, transactions: List[Dict], target_address: str) -> Dict:
        """Calculate comprehensive privacy score based on transaction patterns"""
        if not transactions:
            return {'score': 0, 'factors': {}, 'recommendations': [], 'details': {}}
        
        factors = {}
        recommendations = []
        details = {}
        
        # Factor 1: Address reuse analysis
        unique_addresses = set()
        total_interactions = 0
        address_usage = {}
        
        for tx in transactions:
            if 'inputs' in tx:
                for inp in tx['inputs']:
                    addr = inp['sender']
                    if addr != 'N/A (script)':
                        unique_addresses.add(addr)
                        total_interactions += 1
                        address_usage[addr] = address_usage.get(addr, 0) + 1
            if 'outputs' in tx:
                for out in tx['outputs']:
                    addr = out['recipient']
                    if addr != 'N/A (script)':
                        unique_addresses.add(addr)
                        total_interactions += 1
                        address_usage[addr] = address_usage.get(addr, 0) + 1
        
        reuse_ratio = len(unique_addresses) / max(total_interactions, 1)
        factors['address_diversity'] = min(reuse_ratio * 100, 100)
        
        # Count how many times target address is reused
        target_reuse = address_usage.get(target_address, 0)
        details['address_reuse_count'] = target_reuse
        details['unique_addresses'] = len(unique_addresses)
        details['total_interactions'] = total_interactions
        
        if reuse_ratio < 0.5:
            recommendations.append("Consider using a new address for each transaction to improve privacy")
        if target_reuse > 5:
            recommendations.append(f"Target address used {target_reuse} times - high reuse reduces privacy")
        
        # Factor 2: Transaction timing patterns
        timestamps = [tx['timestamp'] for tx in transactions if tx.get('timestamp')]
        if len(timestamps) > 1:
            timestamps.sort()
            intervals = [timestamps[i+1] - timestamps[i] for i in range(len(timestamps)-1)]
            avg_interval = sum(intervals) / len(intervals)
            
            # Check for regular patterns (bad for privacy)
            regular_pattern = sum(1 for interval in intervals if abs(interval - avg_interval) < 3600) / len(intervals)
            factors['timing_randomness'] = (1 - regular_pattern) * 100
            
            details['avg_time_between_tx'] = avg_interval / 3600  # hours
            details['regular_timing_pattern'] = regular_pattern > 0.7
            
            if regular_pattern > 0.7:
                recommendations.append("Vary transaction timing to avoid predictable patterns")
        else:
            factors['timing_randomness'] = 50  # neutral score for insufficient data
            details['avg_time_between_tx'] = 0
        
        # Factor 3: Transaction amounts analysis
        amounts = []
        for tx in transactions:
            if 'outputs' in tx:
                amounts.extend([out['value'] for out in tx['outputs']])
        
        if amounts:
            # Check for round numbers (bad for privacy)
            round_amounts = sum(1 for amount in amounts if amount % 100000 == 0)
            factors['amount_diversity'] = max(0, 100 - (round_amounts / len(amounts)) * 100)
            
            # Check for common amounts
            amount_counts = {}
            for amount in amounts:
                amount_counts[amount] = amount_counts.get(amount, 0) + 1
            
            repeated_amounts = sum(1 for count in amount_counts.values() if count > 1)
            details['round_amounts_ratio'] = round_amounts / len(amounts)
            details['repeated_amounts'] = repeated_amounts
            
            if round_amounts / len(amounts) > 0.3:
                recommendations.append("Avoid round number amounts to improve transaction privacy")
        else:
            factors['amount_diversity'] = 50
            details['round_amounts_ratio'] = 0
        
        # Factor 4: Input/Output patterns analysis
        input_counts = [tx.get('input_count', 1) for tx in transactions]
        output_counts = [tx.get('output_count', 1) for tx in transactions]
        
        # Simple transactions (1 input, 2 outputs) are common and provide some privacy
        simple_tx_ratio = sum(1 for i, o in zip(input_counts, output_counts) if i == 1 and o == 2) / len(transactions)
        complex_tx_ratio = sum(1 for i, o in zip(input_counts, output_counts) if i > 3 or o > 3) / len(transactions)
        
        factors['transaction_structure'] = min(simple_tx_ratio * 100 + 20, 100)
        details['simple_tx_ratio'] = simple_tx_ratio
        details['complex_tx_ratio'] = complex_tx_ratio
        
        if simple_tx_ratio < 0.3:
            recommendations.append("Consider using simple transaction structures (1 input, 2 outputs) for better privacy")
        if complex_tx_ratio > 0.3:
            recommendations.append("High complexity transactions may stand out - consider simpler patterns")
        
        # Factor 5: Script type diversity
        script_types = set()
        for tx in transactions:
            if 'inputs' in tx:
                script_types.update(inp.get('script_type', 'unknown') for inp in tx['inputs'])
            if 'outputs' in tx:
                script_types.update(out.get('script_type', 'unknown') for out in tx['outputs'])
        
        factors['script_diversity'] = min(len(script_types) * 25, 100)
        details['script_types_used'] = list(script_types)
        
        # Factor 6: Transaction size consistency
        sizes = [tx.get('size', 0) for tx in transactions if tx.get('size', 0) > 0]
        if sizes:
            avg_size = sum(sizes) / len(sizes)
            size_variance = sum((size - avg_size) ** 2 for size in sizes) / len(sizes)
            size_consistency = max(0, 100 - (size_variance / avg_size) * 10)
            factors['size_consistency'] = min(size_consistency, 100)
            details['avg_tx_size'] = avg_size
        else:
            factors['size_consistency'] = 50
        
        # Calculate overall score with weights
        weights = {
            'address_diversity': 0.3,
            'timing_randomness': 0.2,
            'amount_diversity': 0.2,
            'transaction_structure': 0.15,
            'script_diversity': 0.1,
            'size_consistency': 0.05
        }
        
        weighted_score = sum(factors[factor] * weights[factor] for factor in factors)
        
        return {
            'score': round(weighted_score, 2),
            'factors': factors,
            'recommendations': recommendations,
            'details': details
        }
    
    def analyze_privacy_score(self, address: str, max_transactions: int = 10):
        """Analyze privacy score for a given address"""
        print(f"🔒 Calculating privacy score for {address[:20]}...")
        
        # Get transaction summary
        transactions_summary = self.api_client.get_address_transactions(address, limit=50)
        if not transactions_summary:
            print("❌ No transactions found or failed to fetch transaction data.")
            return
        
        # Get detailed transaction data (limited for performance)
        all_full_tx_data = []
        processed_count = 0
        
        for tx_summary in transactions_summary:
            if processed_count >= max_transactions:
                break
                
            tx_data = self.api_client.get_transaction_data(tx_summary['hash'])
            if tx_data:
                all_full_tx_data.append(tx_data)
                processed_count += 1
        
        if not all_full_tx_data:
            print("❌ Failed to fetch detailed transaction data.")
            return
        
        # Calculate privacy score
        privacy_analysis = self.calculate_privacy_score(all_full_tx_data, address)
        
        # Display results
        self.display_privacy_report(address, all_full_tx_data, privacy_analysis)
    
    def display_privacy_report(self, address: str, transactions: List[Dict], analysis: Dict):
        """Display comprehensive privacy analysis report"""
        print("\n" + "="*70)
        print("🔒 BITCOIN PRIVACY ANALYSIS REPORT")
        print("="*70)
        print(f"📍 Address: {address}")
        print(f"📊 Transactions analyzed: {len(transactions)}")
        print(f"🏆 Overall Privacy Score: {analysis['score']:.1f}/100")
        
        # Score interpretation
        score = analysis['score']
        if score >= 80:
            status = "🟢 EXCELLENT"
            advice = "Your transaction patterns show good privacy practices"
        elif score >= 60:
            status = "🟡 GOOD" 
            advice = "Good privacy with room for improvement"
        elif score >= 40:
            status = "🟠 MODERATE"
            advice = "Some privacy concerns - consider implementing recommendations"
        else:
            status = "🔴 POOR"
            advice = "Significant privacy risks detected - action recommended"
        
        print(f"📈 Privacy Level: {status}")
        print(f"💬 {advice}")
        
        print("\n📋 DETAILED PRIVACY FACTORS:")
        for factor, value in analysis['factors'].items():
            emoji = "🟢" if value >= 70 else "🟡" if value >= 50 else "🔴"
            print(f"   {emoji} {factor.replace('_', ' ').title()}: {value:.1f}/100")
        
        # Additional details
        details = analysis.get('details', {})
        if details:
            print("\n📊 TRANSACTION STATISTICS:")
            if 'address_reuse_count' in details:
                print(f"   • Address reuse count: {details['address_reuse_count']}")
            if 'unique_addresses' in details:
                print(f"   • Unique addresses interacted with: {details['unique_addresses']}")
            if 'avg_time_between_tx' in details:
                print(f"   • Average time between transactions: {details['avg_time_between_tx']:.1f} hours")
            if 'round_amounts_ratio' in details:
                print(f"   • Round number amounts: {details['round_amounts_ratio']:.1%}")
            if 'script_types_used' in details:
                print(f"   • Script types used: {', '.join(details['script_types_used'])}")
        
        if analysis['recommendations']:
            print("\n💡 PRIVACY RECOMMENDATIONS:")
            for i, rec in enumerate(analysis['recommendations'], 1):
                print(f"   {i}. {rec}")
        
        # Export option
        export_choice = input("\n💾 Export analysis to CSV? (y/n): ").strip().lower()
        if export_choice == 'y':
            self.export_analysis_to_csv(address, transactions, analysis)
        
        print("\n" + "="*70)
    
    def export_analysis_to_csv(self, address: str, transactions: List[Dict], analysis: Dict):
        """Export analysis results to CSV file"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"bitcoin_privacy_analysis_{address[:12]}_{timestamp}.csv"
        
        try:
            with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
                writer = csv.writer(csvfile)
                
                # Write header
                writer.writerow(['Bitcoin Privacy Analysis Report'])
                writer.writerow(['Address', address])
                writer.writerow(['Analysis Date', datetime.now().isoformat()])
                writer.writerow(['Overall Score', f"{analysis['score']:.1f}/100"])
                writer.writerow([])
                
                # Write factors
                writer.writerow(['Privacy Factors'])
                writer.writerow(['Factor', 'Score'])
                for factor, value in analysis['factors'].items():
                    writer.writerow([factor.replace('_', ' ').title(), f"{value:.1f}"])
                writer.writerow([])
                
                # Write recommendations
                writer.writerow(['Recommendations'])
                for i, rec in enumerate(analysis['recommendations'], 1):
                    writer.writerow([f"{i}.", rec])
                writer.writerow([])
                
                # Write transaction details
                writer.writerow(['Transaction Details'])
                writer.writerow(['Hash', 'Block Height', 'Timestamp', 'Fee', 'Inputs', 'Outputs'])
                for tx in transactions:
                    timestamp_str = datetime.fromtimestamp(tx['timestamp']).isoformat() if tx.get('timestamp') else 'Unconfirmed'
                    writer.writerow([
                        tx['hash'],
                        tx.get('block_id', 'Unconfirmed'),
                        timestamp_str,
                        tx.get('fee', 0),
                        len(tx.get('inputs', [])),
                        len(tx.get('outputs', []))
                    ])
            
            print(f"✅ Analysis exported to {filename}")
            
        except Exception as e:
            print(f"❌ Failed to export analysis: {e}")

def interactive_address_input(api_client: BlockchainAPIClient) -> Optional[str]:
    """Interactive address input with validation"""
    while True:
        address = input("Enter Bitcoin address: ").strip()
        
        if not address:
            print("❌ Please enter a valid Bitcoin address.")
            continue
        
        # Basic format validation
        if not (address.startswith(('1', '3', 'bc1', 'tb1')) and len(address) >= 25):
            print("❌ Invalid Bitcoin address format.")
            print("   Supported formats: Legacy (1...), P2SH (3...), Bech32 (bc1...)")
            continue
        
        # Validate address exists on blockchain
        if api_client.validate_address(address):
            return address
        else:
            retry = input("Would you like to try another address? (y/n): ").strip().lower()
            if retry != 'y':
                return None

def display_help():
    """Display help information"""
    print("\n" + "="*60)
    print("🔒 BITCOIN PRIVACY ANALYZER - HELP")
    print("="*60)
    print("This tool analyzes Bitcoin address transaction patterns")
    print("to assess privacy levels and provide recommendations.")
    print()
    print("🔍 PRIVACY FACTORS ANALYZED:")
    print("• Address Diversity - How often addresses are reused")
    print("• Timing Patterns - Regularity of transaction timing")
    print("• Amount Diversity - Use of round vs random amounts")
    print("• Transaction Structure - Complexity of inputs/outputs")
    print("• Script Diversity - Variety of script types used")
    print("• Size Consistency - Variation in transaction sizes")
    print()
    print("📊 SCORING SYSTEM:")
    print("• 80-100: Excellent privacy practices")
    print("• 60-79:  Good privacy with minor improvements")
    print("• 40-59:  Moderate privacy, some risks")
    print("• 0-39:   Poor privacy, significant risks")
    print()
    print("💡 TIPS FOR BETTER PRIVACY:")
    print("• Use a new address for each transaction")
    print("• Vary transaction timing randomly")
    print("• Avoid round number amounts")
    print("• Use simple transaction structures when possible")
    print("• Consider using privacy-focused wallets")
    print("="*60)

def main():
    """Main function with enhanced menu system"""
    print("="*70)
    print("🔒 ENHANCED BITCOIN PRIVACY ANALYZER")
    print("="*70)
    print("Advanced analysis of Bitcoin address privacy patterns")
    print("with comprehensive scoring and recommendations.")
    print("-"*70)
    
    api_client = BlockchainAPIClient()
    analyzer = CryptocurrencyPrivacyAnalyzer(api_client)
    
    while True:
        print("\n📋 MAIN MENU:")
        print("1. 🔍 Analyze address privacy")
        print("2. ❓ Help & Information")
        print("3. ⚙️  Settings")
        print("4. 🚪 Exit")
        
        choice = input("\nEnter your choice (1-4): ").strip()
        
        if choice == '1':
            address = interactive_address_input(api_client)
            if address:
                # Ask for number of transactions to analyze
                while True:
                    try:
                        max_tx = input("Number of transactions to analyze (1-50, default 10): ").strip()
                        max_tx = int(max_tx) if max_tx else 10
                        max_tx = min(max(max_tx, 1), 50)  # Clamp between 1-50
                        break
                    except ValueError:
                        print("❌ Please enter a valid number.")
                
                analyzer.analyze_privacy_score(address, max_tx)
                
        elif choice == '2':
            display_help()
            
        elif choice == '3':
            print("\n⚙️  SETTINGS:")
            print(f"Current API: {api_client.selected_api.title()}")
            print(f"Rate limit delay: {api_client.rate_limit_delay}s")
            print("(Settings modification not implemented in this version)")
            
        elif choice == '4':
            print("\n👋 Thank you for using Enhanced Bitcoin Privacy Analyzer!")
            print("Stay safe and protect your privacy! 🔐")
            break
            
        else:
            print("❌ Invalid choice. Please enter 1-4.")

if __name__ == "__main__":
    main()


# In[ ]:




