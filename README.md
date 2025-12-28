# Uniswap V3 Position Query Tool

A Python tool to query and track your Uniswap V3 liquidity positions, including deposits, fees, and position history.

## Features

- 📊 **Position Overview**: Query all your Uniswap V3 LP positions with current amounts, values, and status
- 💰 **Fee Tracking**: Calculate accumulated fees (both collected and uncollected)
- 📈 **Deposit History**: Track all deposits made to each position with historical prices
- 💾 **CSV Export**: Automatically save data to CSV files with append-only tracking
- 🔄 **Incremental Updates**: Positions append each run, deposits deduplicate automatically
- ⚡ **Optimized**: Caching reduces RPC calls for better performance

## Requirements

- Python 3.8+
- `web3` library

## Installation

```bash
pip install web3
```

## Configuration

**Important**: `config.json` contains placeholders. You must update it with your own values before running the script.

1. Copy the example config (or edit `config.json` directly):
   ```bash
   cp config.example.json config.json
   ```

2. Edit `config.json` with your settings:

```json
{
  "rpc_url": "https://mainnet.infura.io/v3/YOUR_API_KEY",
  "owner": "0xYourWalletAddress",
  ...
}
```

### Required Configuration

1. **RPC URL**: Your Ethereum RPC endpoint (Infura, Alchemy, etc.)
   - For historical price queries, an archive node is recommended
   - Free tier RPCs may not support historical state queries
   - ⚠️ **Do not commit your actual RPC URL/API key to version control**

2. **Owner Address**: Your wallet address (0x format)
   - ⚠️ **Consider whether you want to commit your wallet address**

3. **Addresses**: Pre-configured for Uniswap V3 mainnet contracts (no changes needed)

### Security Note

The repository's `config.json` contains placeholders. Always use your own `config.json` with actual credentials locally and never commit sensitive information like API keys to the repository.

## Usage

```bash
python query_v3_positions.py
```

The script will:
1. Query all your Uniswap V3 positions
2. Calculate current token amounts and values
3. Track accumulated fees
4. Retrieve deposit history with historical prices
5. Display results in formatted tables
6. Save data to `positions.csv` and `deposits.csv`

## Output Files

### positions.csv
Contains position snapshots with:
- TokenID, Pair, Fee tier, Status
- Current token amounts and total value
- Price range and tick range
- Uncollected fees
- Accumulated fees (total earned)
- Query timestamp

**Note**: Each script run appends a new row, creating a historical record of your positions.

### deposits.csv
Contains all deposits made to positions with:
- TokenID, Pair
- Deposit date/block
- Amounts (token0 and token1)
- Price at deposit time
- Deposit value
- Transaction hash

**Note**: Duplicates are automatically prevented based on transaction hash.

## Example Output

```
================================================================================
                               POSITIONS OVERVIEW                               
================================================================================

TokenID | Pair      | Fee  | Status                | Current Amounts            | ...
1157630 | WETH/USDT | 0.3% | ACTIVE (earning fees) | 0.1421 WETH, 194.8475 USDT | ...
```

## Features Explained

### Position Status
- **ACTIVE (earning fees)**: Current price is within your tick range
- **OUT OF RANGE (below)**: Price dropped below your range - position holds only token0
- **OUT OF RANGE (above)**: Price rose above your range - position holds only token1

### Fee Tracking
- **Uncollected Fees**: Fees ready to be collected (shown as tokensOwed)
- **Accumulated Fees**: Total fees earned since position creation
- **Fees Value**: Total USD value of accumulated fees

### Historical Prices
- Historical deposit prices are queried from the blockchain
- Requires archive node RPC support for historical state queries
- If unavailable, deposit values are calculated using current price (marked with `*`)

## CSV Data Management

The tool automatically manages CSV files:

- **First Run**: Creates new `positions.csv` and `deposits.csv`
- **Subsequent Runs**: 
  - Positions: Appends new rows (each run captures current state)
  - Deposits: Only adds new deposits (checks for duplicates by transaction hash)

This ensures you have:
- Historical position snapshots over time
- Complete deposit history without duplicates

## RPC Limitations

**Free Tier RPCs** (like Infura free tier):
- ✅ Support current state queries
- ❌ May not support historical state queries
- ⚠️ Result: Historical deposit prices may show as "N/A"

**Archive Node RPCs** (recommended):
- ✅ Full historical state access
- ✅ Accurate historical price queries
- 💡 Available from: Infura/Alchemy paid plans, QuickNode, etc.

## Project Structure

```
AMM-Manager/
├── query_v3_positions.py  # Main script
├── config.json            # Configuration (RPC, addresses, ABIs)
├── positions.csv          # Position snapshots (auto-generated)
├── deposits.csv           # Deposit history (auto-generated)
└── README.md              # This file
```

## Code Architecture

The tool is organized into classes:

- **UniswapV3Query**: Main query class handling all blockchain interactions
- **TableFormatter**: Handles table display and CSV export with append/deduplication logic

All contract ABIs are stored in `config.json` for easy updates.

## Contributing

Feel free to submit issues or pull requests!

## License

MIT License

