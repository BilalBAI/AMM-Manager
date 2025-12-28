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
- `python-dotenv` library

## Installation

```bash
pip install -r requirements.txt
```

Or install manually:
```bash
pip install web3 python-dotenv
```

## Configuration

### 1. Create `.env` file

Copy the example environment file and edit it with your credentials:

```bash
cp .env.example .env
```

Edit `.env` with your settings:

```env
RPC_URL=https://mainnet.infura.io/v3/YOUR_API_KEY
OWNER_ADDRESS=0xYourWalletAddress
```

### Required Environment Variables

1. **RPC_URL**: Your Ethereum RPC endpoint
   - Infura: `https://mainnet.infura.io/v3/YOUR_API_KEY`
   - Alchemy: `https://eth-mainnet.g.alchemy.com/v2/YOUR_API_KEY`
   - Public: `https://eth.llamarpc.com`
   - For historical price queries, an archive node is recommended
   - Free tier RPCs may not support historical state queries

2. **OWNER_ADDRESS**: Your wallet address (0x format)

### Configuration Files

- **`.env`**: Contains your sensitive credentials (never commit this file)
- **`config.json`**: Contains contract addresses and ABIs (safe to commit)

### Security Note

- ✅ `.env` is in `.gitignore` - your credentials won't be committed
- ✅ Only `.env.example` (with placeholders) is in the repository
- ⚠️ Never commit your actual `.env` file to version control

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

