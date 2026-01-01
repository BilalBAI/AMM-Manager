from web3 import Web3
from datetime import datetime
import csv
import json
import math
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


class UniswapV3Query:
    """Main class for querying Uniswap V3 positions"""

    Q96 = 2 ** 96

    def __init__(self, config_path='config.json'):
        with open(config_path) as f:
            self.config = json.load(f)

        # Load sensitive data from environment variables
        rpc_url = os.getenv('RPC_URL')
        owner = os.getenv('OWNER_ADDRESS')

        if not rpc_url:
            raise ValueError(
                "RPC_URL environment variable is required. Please set it in .env file")
        if not owner:
            raise ValueError(
                "OWNER_ADDRESS environment variable is required. Please set it in .env file")

        self.w3 = Web3(Web3.HTTPProvider(rpc_url))
        self.owner = Web3.toChecksumAddress(owner)
        self.nfpm = self.w3.eth.contract(
            Web3.toChecksumAddress(self.config['addresses']['nfpm']),
            abi=self.config['abis']['nfpm']
        )
        self.factory = self.w3.eth.contract(
            Web3.toChecksumAddress(self.config['addresses']['factory']),
            abi=self.config['abis']['factory']
        )
        self.token_cache = {}
        self.pool_cache = {}

    def _get_token_info(self, address):
        """Get token decimals and symbol (cached)"""
        if address not in self.token_cache:
            contract = self.w3.eth.contract(
                address, abi=self.config['abis']['erc20'])
            self.token_cache[address] = {
                'decimals': contract.functions.decimals().call(),
                'symbol': contract.functions.symbol().call()
            }
        return self.token_cache[address]

    def _get_pool_address(self, token0, token1, fee):
        """Get pool address (cached)"""
        key = (token0, token1, fee)
        if key not in self.pool_cache:
            self.pool_cache[key] = self.factory.functions.getPool(
                token0, token1, fee).call()
        return self.pool_cache[key]

    @staticmethod
    def tick_to_price(tick, dec0, dec1):
        """Convert tick to human-readable price"""
        return (1.0001 ** tick) * (10 ** dec0) / (10 ** dec1)

    @staticmethod
    def tick_to_sqrt_price(tick):
        """Convert tick to sqrt price"""
        return 1.0001 ** (tick / 2)

    def _get_amounts_from_liquidity(self, L, sqrt_price_x96, tick, tickL, tickU, dec0, dec1):
        """Calculate token amounts from liquidity"""
        sqrt_pl = self.tick_to_sqrt_price(tickL)
        sqrt_pu = self.tick_to_sqrt_price(tickU)
        sqrt_pc = sqrt_pl if tick < tickL else (
            sqrt_pu if tick > tickU else sqrt_price_x96 / self.Q96)

        if tick < tickL:
            return L * (1/sqrt_pl - 1/sqrt_pu) / (10**dec0), 0
        elif tick > tickU:
            return 0, L * (sqrt_pu - sqrt_pl) / (10**dec1)
        else:
            return (L * (1/sqrt_pc - 1/sqrt_pu) / (10**dec0),
                    L * (sqrt_pc - sqrt_pl) / (10**dec1))

    def _calculate_fee_growth_inside(self, pool, tick_lower, tick_upper, current_tick):
        """Calculate fee growth inside the tick range"""
        try:
            # Get global fee growth
            fee_growth_global_0 = pool.functions.feeGrowthGlobal0X128().call()
            fee_growth_global_1 = pool.functions.feeGrowthGlobal1X128().call()

            # Get fee growth outside at lower tick
            tick_lower_data = pool.functions.ticks(tick_lower).call()
            fee_growth_outside_0_lower = tick_lower_data[2]
            fee_growth_outside_1_lower = tick_lower_data[3]

            # Get fee growth outside at upper tick
            tick_upper_data = pool.functions.ticks(tick_upper).call()
            fee_growth_outside_0_upper = tick_upper_data[2]
            fee_growth_outside_1_upper = tick_upper_data[3]

            # Calculate fee growth below lower tick
            if current_tick >= tick_lower:
                fee_growth_below_0 = fee_growth_outside_0_lower
                fee_growth_below_1 = fee_growth_outside_1_lower
            else:
                fee_growth_below_0 = fee_growth_global_0 - fee_growth_outside_0_lower
                fee_growth_below_1 = fee_growth_global_1 - fee_growth_outside_1_lower

            # Calculate fee growth above upper tick
            if current_tick < tick_upper:
                fee_growth_above_0 = fee_growth_outside_0_upper
                fee_growth_above_1 = fee_growth_outside_1_upper
            else:
                fee_growth_above_0 = fee_growth_global_0 - fee_growth_outside_0_upper
                fee_growth_above_1 = fee_growth_global_1 - fee_growth_outside_1_upper

            # Fee growth inside = global - below - above
            fee_growth_inside_0 = fee_growth_global_0 - \
                fee_growth_below_0 - fee_growth_above_0
            fee_growth_inside_1 = fee_growth_global_1 - \
                fee_growth_below_1 - fee_growth_above_1

            return fee_growth_inside_0, fee_growth_inside_1
        except Exception:
            return None, None

    def _calculate_accumulated_fees(self, pool, liquidity, tick_lower, tick_upper, current_tick,
                                    fee_growth_inside_0_last, fee_growth_inside_1_last,
                                    tokens_owed_0, tokens_owed_1, dec0, dec1):
        """Calculate total accumulated fees (both collected and uncollected)"""
        try:
            fee_growth_inside_0, fee_growth_inside_1 = self._calculate_fee_growth_inside(
                pool, tick_lower, tick_upper, current_tick)

            if fee_growth_inside_0 is None or fee_growth_inside_1 is None:
                return None, None

            # Calculate fees accrued since last update
            Q128 = 2 ** 128
            fee_growth_delta_0 = fee_growth_inside_0 - fee_growth_inside_0_last
            fee_growth_delta_1 = fee_growth_inside_1 - fee_growth_inside_1_last

            # Fees owed from growth
            fees_from_growth_0 = (liquidity * fee_growth_delta_0) // Q128
            fees_from_growth_1 = (liquidity * fee_growth_delta_1) // Q128

            # Total accumulated fees = fees from growth + tokens already owed
            total_fees_0 = fees_from_growth_0 + tokens_owed_0
            total_fees_1 = fees_from_growth_1 + tokens_owed_1

            return (total_fees_0 / (10**dec0), total_fees_1 / (10**dec1))
        except Exception:
            return None, None

    def _get_historical_price(self, pool_addr, block_num, dec0, dec1):
        """Get pool price at historical block.
        Note: Requires archive node RPC support for historical state queries.
        Free tier RPCs (like Infura) often don't support this.
        """
        if not pool_addr:
            return None
        try:
            pool = self.w3.eth.contract(
                pool_addr, abi=self.config['abis']['pool'])
            # Try querying at the block - this may fail if RPC doesn't support historical queries
            slot0 = pool.functions.slot0().call(block_identifier=block_num)
            if not slot0 or not slot0[0]:
                return None
            sqrt_price_x96 = slot0[0]
            price = (sqrt_price_x96 / self.Q96) ** 2
            return price * (10**dec0) / (10**dec1)
        except Exception:
            # Common causes:
            # 1. RPC endpoint doesn't support historical state queries (free tier limitation)
            # 2. Block too old and requires archive node
            # 3. Rate limiting or timeout
            return None

    def _get_all_deposits(self, token_id, dec0, dec1, pool_addr=None):
        """Get all IncreaseLiquidity events for a position"""
        deposits = []
        try:
            contract = self.w3.eth.contract(
                self.nfpm.address, abi=[
                    self.config['abis']['increaseLiquidityEvent']]
            )
            sig = self.w3.keccak(
                text="IncreaseLiquidity(uint256,uint128,uint256,uint256)").hex()
            token_topic = "0x" + hex(token_id)[2:].zfill(64)

            cb = self.w3.eth.block_number
            fb = max(self.config['constants']['nfpmDeployBlock'],
                     cb - self.config['constants']['maxBlockLookback'])

            logs = self.w3.eth.get_logs({
                "fromBlock": fb, "toBlock": "latest",
                "address": self.nfpm.address,
                "topics": [sig, token_topic]
            })

            for log in logs:
                try:
                    decoded = contract.events.IncreaseLiquidity().processLog(log)
                    if decoded['args']['tokenId'] == token_id:
                        a0 = decoded['args']['amount0'] / (10**dec0)
                        a1 = decoded['args']['amount1'] / (10**dec1)
                        block = log['blockNumber']
                        tx = log['transactionHash'].hex()

                        try:
                            ts = datetime.fromtimestamp(
                                self.w3.eth.get_block(block)['timestamp'])
                        except:
                            ts = None

                        price = None
                        if pool_addr:
                            price = self._get_historical_price(
                                pool_addr, block, dec0, dec1)
                        deposits.append((a0, a1, block, tx, price, ts))
                except:
                    continue

            deposits.sort(key=lambda x: x[2])
        except:
            pass
        return deposits

    def _calculate_impermanent_loss(self, deposits, current_price, current_position_value, current_amount0=None, current_amount1=None):
        """Calculate impermanent loss using Approach 1:
        IL = (Current Position Value - Hold Value) / Hold Value × 100%
        where Hold Value = Σ(initial_amount0) × current_price + Σ(initial_amount1)

        Args:
            deposits: List of tuples (amount0, amount1, block, tx, price, timestamp)
            current_price: Current pool price (in token1 per token0)
            current_position_value: Current value of position in token1 terms (may be None)
            current_amount0: Current amount of token0 (for recalculating value if needed)
            current_amount1: Current amount of token1 (for recalculating value if needed)

        Returns:
            IL percentage as float, or None if calculation not possible
        """
        if not deposits or current_price is None:
            return None

        # Recalculate current position value if not provided or if None
        if current_position_value is None:
            if current_amount0 is not None and current_amount1 is not None:
                current_position_value = current_amount0 * current_price + current_amount1
            else:
                return None

        # Sum all initial deposits
        total_initial_amount0 = sum(dep[0] for dep in deposits)
        total_initial_amount1 = sum(dep[1] for dep in deposits)

        # Calculate Hold Value: what the initial tokens would be worth if just held
        hold_value = total_initial_amount0 * current_price + total_initial_amount1

        if hold_value == 0:
            return None

        # Calculate IL
        il = ((current_position_value - hold_value) / hold_value) * 100

        return il

    def query_positions(self):
        """Query all positions and return data for tables"""
        token_ids = [self.nfpm.functions.tokenOfOwnerByIndex(self.owner, i).call()
                     for i in range(self.nfpm.functions.balanceOf(self.owner).call())]
        query_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        positions_data = []
        deposits_data = []

        for tid in token_ids:
            pos = self.nfpm.functions.positions(tid).call()
            _, _, t0, t1, fee, tickL, tickU, L, fee_growth_0_last, fee_growth_1_last, owed0, owed1 = pos

            t0_info = self._get_token_info(t0)
            t1_info = self._get_token_info(t1)
            dec0, dec1 = t0_info['decimals'], t1_info['decimals']
            sym0, sym1 = t0_info['symbol'], t1_info['symbol']

            pool_addr = self._get_pool_address(t0, t1, fee)
            if not pool_addr or pool_addr == "0x" + "0" * 40:
                positions_data.append(
                    [tid, f"{sym0}/{sym1}", f"{fee/10000}%", "Pool not found"] + ["N/A"] * 11 + [query_time])
                continue

            pool = self.w3.eth.contract(
                pool_addr, abi=self.config['abis']['pool'])
            slot0 = pool.functions.slot0().call()
            current_tick, sqrt_price_x96 = slot0[1], slot0[0]

            price = ((sqrt_price_x96 / self.Q96) ** 2) * \
                (10**dec0) / (10**dec1)
            status = ("ACTIVE (earning fees)" if tickL <= current_tick <= tickU else
                      "OUT OF RANGE (below)" if current_tick < tickL else "OUT OF RANGE (above)")

            a0, a1 = self._get_amounts_from_liquidity(
                L, sqrt_price_x96, current_tick, tickL, tickU, dec0, dec1)
            # Calculate value even if one amount is 0 (out of range)
            value = a0 * price + a1

            price_lower = self.tick_to_price(tickL, dec0, dec1)
            price_upper = self.tick_to_price(tickU, dec0, dec1)

            # Calculate accumulated fees
            acc_fees_0, acc_fees_1 = self._calculate_accumulated_fees(
                pool, int(L), tickL, tickU, current_tick,
                fee_growth_0_last, fee_growth_1_last,
                owed0, owed1, dec0, dec1
            )

            # Format fees
            uncollected_fees = f"{owed0/(10**dec0):.4f} {sym0}, {owed1/(10**dec1):.4f} {sym1}"
            if acc_fees_0 is not None and acc_fees_1 is not None:
                acc_fees_str = f"{acc_fees_0:.4f} {sym0}, {acc_fees_1:.4f} {sym1}"
                # Calculate fee value in token1 terms
                fee_value = acc_fees_0 * price + acc_fees_1 if price else None
                acc_fees_value_str = f"{fee_value:.2f} {sym1}" if fee_value else "N/A"
            else:
                acc_fees_str = "N/A"
                acc_fees_value_str = "N/A"

            # Get all deposits for IL calculation
            deposits = self._get_all_deposits(tid, dec0, dec1, pool_addr)

            # Calculate Impermanent Loss
            il = self._calculate_impermanent_loss(
                deposits, price, value, a0, a1)
            il_str = f"{il:.4f}%" if il is not None else "N/A"

            positions_data.append([
                tid, f"{sym0}/{sym1}", f"{fee/10000}%", status,
                f"{price:.6f} {sym1}/{sym0}",
                f"{a0:.4f} {sym0}, {a1:.4f} {sym1}",
                f"{value:.2f} {sym1}" if value is not None else "N/A",
                f"{price_lower:.2f}-{price_upper:.2f}",
                f"{tickL} to {tickU}",
                uncollected_fees,
                acc_fees_str,
                acc_fees_value_str,
                il_str,
                query_time
            ])

            for a0_dep, a1_dep, block, tx, dep_price, ts in deposits:
                time_str = ts.strftime(
                    "%Y-%m-%d %H:%M:%S") if ts else f"Block {block}"
                if dep_price:
                    dep_value = a0_dep * dep_price + a1_dep
                    dep_value_str = f"{dep_value:.2f} {sym1}"
                    price_str = f"{dep_price:.2f}"
                elif price:
                    dep_value_str = f"~{a0_dep * price + a1_dep:.2f} {sym1}*"
                    price_str = "N/A"
                else:
                    dep_value_str = price_str = "N/A"

                deposits_data.append([
                    tid, f"{sym0}/{sym1}", time_str,
                    f"{a0_dep:.4f} {sym0}", f"{a1_dep:.4f} {sym1}",
                    price_str, dep_value_str, tx[:10] + "..."
                ])

        return positions_data, deposits_data


class TableFormatter:
    """Handle table display and CSV export"""

    @staticmethod
    def print_table(headers, rows, title=None):
        """Print formatted table"""
        if title:
            print(f"\n{'='*80}\n{title:^80}\n{'='*80}")

        if not rows:
            print("  No data available")
            return

        widths = [len(str(h)) for h in headers]
        for row in rows:
            for i, cell in enumerate(row[:len(headers)]):
                widths[i] = max(widths[i], len(str(cell)))

        header_row = " | ".join(str(h).ljust(
            widths[i]) for i, h in enumerate(headers))
        print(f"\n{header_row}\n{'-'*len(header_row)}")

        for row in rows:
            print(" | ".join(str(cell).ljust(
                widths[i]) for i, cell in enumerate(row[:len(headers)])))
        print()

    @staticmethod
    def save_csv(headers, rows, filename, is_deposits=False):
        """Save table to CSV, appending to existing file if it exists.
        For deposits, checks for duplicates based on Transaction hash.
        """
        try:
            existing_rows = []
            existing_data = set()

            # Read existing data if file exists
            try:
                with open(filename, 'r', newline='', encoding='utf-8') as f:
                    reader = csv.reader(f)
                    existing_headers = next(reader, None)
                    if existing_headers:
                        existing_rows = list(reader)

                        # For deposits, create a set of existing transactions for deduplication
                        if is_deposits and existing_headers:
                            tx_index = existing_headers.index(
                                'Transaction') if 'Transaction' in existing_headers else None
                            if tx_index is not None:
                                for row in existing_rows:
                                    if len(row) > tx_index:
                                        existing_data.add(row[tx_index])
            except FileNotFoundError:
                pass

            # Filter new rows for deposits (remove duplicates)
            if is_deposits:
                tx_index = headers.index(
                    'Transaction') if 'Transaction' in headers else None
                new_rows = []
                added_count = 0
                for row in rows:
                    if tx_index is not None and len(row) > tx_index:
                        tx_hash = row[tx_index]
                        if tx_hash not in existing_data:
                            new_rows.append(row)
                            existing_data.add(tx_hash)
                            added_count += 1
                    else:
                        new_rows.append(row)
                        added_count += 1

                rows = existing_rows + new_rows
                if added_count > 0:
                    print(
                        f"  ✓ Added {added_count} new deposit(s) to {filename} (total: {len(rows)})")
                else:
                    print(
                        f"  ✓ No new deposits to add to {filename} (total: {len(rows)})")
            else:
                # For positions, always append all new data
                rows = existing_rows + rows
                print(
                    f"  ✓ Appended {len(rows) - len(existing_rows)} position record(s) to {filename} (total: {len(rows)})")

            # Write combined data
            with open(filename, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(headers)
                writer.writerows(rows)
        except Exception as e:
            print(f"  ✗ Error saving {filename}: {e}")


if __name__ == "__main__":
    query = UniswapV3Query()
    pos_data, dep_data = query.query_positions()

    pos_headers = ["TokenID", "Pair", "Fee", "Status", "Current Price",
                   "Current Amounts", "Current Value", "Price Range", "Tick Range",
                   "Uncollected Fees", "Accumulated Fees", "Fees Value", "IL (%)", "Query Time"]
    dep_headers = ["TokenID", "Pair", "Date/Block", "Amount0", "Amount1",
                   "Price at Deposit", "Deposit Value", "Transaction"]

    TableFormatter.print_table(pos_headers, pos_data, "POSITIONS OVERVIEW")
    TableFormatter.print_table(dep_headers, dep_data, "ALL DEPOSITS")

    print(f"\n=== Exporting to CSV ===")
    TableFormatter.save_csv(pos_headers, pos_data,
                            "positions.csv", is_deposits=False)
    TableFormatter.save_csv(dep_headers, dep_data,
                            "deposits.csv", is_deposits=True)

    print(f"\n=== Summary ===")
    print(f"Total positions: {len(pos_data)}")
    print(f"Total deposits: {len(dep_data)}")
