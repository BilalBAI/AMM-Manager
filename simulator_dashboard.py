import dash
from dash import dcc, html, Input, Output
import plotly.graph_objs as go
import pandas as pd
import math
from query_v3_positions import UniswapV3Query


class PositionSimulator:
    """Simulate position values at different prices"""

    Q96 = 2 ** 96

    @staticmethod
    def tick_to_price(tick, dec0, dec1):
        """Convert tick to price"""
        return (1.0001 ** tick) * (10 ** dec0) / (10 ** dec1)

    @staticmethod
    def price_to_tick(price, dec0, dec1):
        """Convert price to tick"""
        adjusted_price = price * (10 ** dec1) / (10 ** dec0)
        return int(math.log(adjusted_price, 1.0001))

    @staticmethod
    def tick_to_sqrt_price(tick):
        """Convert tick to sqrt price"""
        return 1.0001 ** (tick / 2)

    @staticmethod
    def get_amounts_at_price(L, price, tick_lower, tick_upper, dec0, dec1):
        """Calculate token amounts at a given price"""
        tick = PositionSimulator.price_to_tick(price, dec0, dec1)
        sqrt_pl = PositionSimulator.tick_to_sqrt_price(tick_lower)
        sqrt_pu = PositionSimulator.tick_to_sqrt_price(tick_upper)
        sqrt_pc = PositionSimulator.tick_to_sqrt_price(tick)

        if tick < tick_lower:
            amount0 = L * (1/sqrt_pl - 1/sqrt_pu) / (10**dec0)
            amount1 = 0
        elif tick > tick_upper:
            amount0 = 0
            amount1 = L * (sqrt_pu - sqrt_pl) / (10**dec1)
        else:
            amount0 = L * (1/sqrt_pc - 1/sqrt_pu) / (10**dec0)
            amount1 = L * (sqrt_pc - sqrt_pl) / (10**dec1)

        return amount0, amount1

    @staticmethod
    def calculate_liquidity_from_amounts(amount0, amount1, price, tick_lower, tick_upper, dec0, dec1):
        """Calculate liquidity from current amounts and price"""
        tick = PositionSimulator.price_to_tick(price, dec0, dec1)
        sqrt_pl = PositionSimulator.tick_to_sqrt_price(tick_lower)
        sqrt_pu = PositionSimulator.tick_to_sqrt_price(tick_upper)
        sqrt_pc = PositionSimulator.tick_to_sqrt_price(tick)

        if tick < tick_lower:
            # All in token0
            if amount0 > 0:
                L = amount0 * (10**dec0) / (1/sqrt_pl - 1/sqrt_pu)
            else:
                L = 0
        elif tick > tick_upper:
            # All in token1
            if amount1 > 0:
                L = amount1 * (10**dec1) / (sqrt_pu - sqrt_pl)
            else:
                L = 0
        else:
            # In range - need to solve for L from both amounts
            # Use whichever gives valid result
            if amount0 > 0:
                L0 = amount0 * (10**dec0) / (1/sqrt_pc - 1/sqrt_pu)
            else:
                L0 = 0
            if amount1 > 0:
                L1 = amount1 * (10**dec1) / (sqrt_pc - sqrt_pl)
            else:
                L1 = 0
            L = max(L0, L1) if (L0 > 0 and L1 > 0) else (L0 if L0 > 0 else L1)

        return L

    @staticmethod
    def simulate_position(pos_data, query_instance=None):
        """Simulate position value at different prices"""
        # Extract position data
        tick_lower = int(pos_data['Tick Range'].split(' to ')[0])
        tick_upper = int(pos_data['Tick Range'].split(' to ')[1])
        
        # Parse pair and get current amounts
        pair = pos_data['Pair']
        tokens = pair.split('/')
        sym0, sym1 = tokens[0], tokens[1]
        
        # Get current amounts
        amounts_str = pos_data.get('Current Amounts', '0 0')
        try:
            parts = amounts_str.split(',')
            amount0_str = parts[0].strip().split()[0]
            amount1_str = parts[1].strip().split()[0] if len(parts) > 1 else '0'
            current_amount0 = float(amount0_str)
            current_amount1 = float(amount1_str)
        except:
            current_amount0 = current_amount1 = 0
        
        # Get current price
        current_price_str = pos_data.get('Current Price', '0')
        try:
            current_price = float(current_price_str.split()[0])
        except:
            current_price = None
        
        # Parse price range
        price_range_str = pos_data.get('Price Range', '0-0')
        try:
            price_min = float(price_range_str.split('-')[0])
            price_max = float(price_range_str.split('-')[1])
        except:
            return None, None, None, None, None
        
        # Determine decimals (default assumptions)
        dec0 = 18 if 'ETH' in sym0 else 6
        dec1 = 18 if 'ETH' in sym1 else 6
        
        # Calculate liquidity from current amounts
        if current_price and (current_amount0 > 0 or current_amount1 > 0):
            L = PositionSimulator.calculate_liquidity_from_amounts(
                current_amount0, current_amount1, current_price,
                tick_lower, tick_upper, dec0, dec1
            )
        else:
            # Fallback: estimate from price range (rough approximation)
            L = 1e15
        
        # Generate price points (wider range for better visualization)
        sim_price_min = price_min * 0.7
        sim_price_max = price_max * 1.3
        steps = 200
        prices = [sim_price_min + (sim_price_max - sim_price_min) * i / steps for i in range(steps + 1)]
        
        # Parse accumulated fees
        acc_fees_str = pos_data.get('Accumulated Fees', 'N/A')
        if acc_fees_str == 'N/A':
            acc_fees_0 = acc_fees_1 = 0
        else:
            try:
                parts = acc_fees_str.split(',')
                acc_fees_0 = float(parts[0].split()[0]) if len(parts) > 0 else 0
                acc_fees_1 = float(parts[1].split()[0]) if len(parts) > 1 else 0
            except:
                acc_fees_0 = acc_fees_1 = 0
        
        current_values = []
        fee_values = []
        
        for price in prices:
            # Calculate position value at this price
            amount0, amount1 = PositionSimulator.get_amounts_at_price(
                L, price, tick_lower, tick_upper, dec0, dec1
            )
            position_value = amount0 * price + amount1
            current_values.append(position_value)
            
            # Calculate fee value at this price (fees value changes with price)
            fee_value = acc_fees_0 * price + acc_fees_1
            fee_values.append(fee_value)
        
        return prices, current_values, fee_values, price_min, price_max, current_price


def load_positions_from_csv():
    """Load latest positions from CSV"""
    try:
        df = pd.read_csv('positions.csv')
        df['Query Time'] = pd.to_datetime(df['Query Time'])
        latest = df.loc[df.groupby('TokenID')['Query Time'].idxmax()]
        return latest.to_dict('records')
    except Exception as e:
        print(f"Error loading positions: {e}")
        return []


def create_simulator_chart(pos_data):
    """Create simulation chart for a position"""
    result = PositionSimulator.simulate_position(pos_data)
    if result[0] is None:
        # Return empty chart if simulation failed
        return go.Figure().update_layout(title="Unable to simulate position")
    
    prices, current_values, fee_values, price_min, price_max, current_price = result
    
    # Create traces
    traces = [
        go.Scatter(
            x=prices,
            y=current_values,
            mode='lines',
            name='Position Value',
            line=dict(color='#2E86AB', width=3),
            hovertemplate='Price: %{x:.2f}<br>Value: %{y:.2f} USD<extra></extra>'
        ),
        go.Scatter(
            x=prices,
            y=fee_values,
            mode='lines',
            name='Fees Value',
            line=dict(color='#A23B72', width=3, dash='dash'),
            hovertemplate='Price: %{x:.2f}<br>Fees Value: %{y:.2f} USD<extra></extra>'
        )
    ]
    
    # Add vertical lines for range boundaries
    y_min = min(min(current_values), min(fee_values))
    y_max = max(max(current_values), max(fee_values))
    y_range = y_max - y_min
    
    traces.append(
        go.Scatter(
            x=[price_min, price_min],
            y=[y_min - y_range * 0.1, y_max + y_range * 0.1],
            mode='lines',
            name='Lower Bound',
            line=dict(color='red', width=2, dash='dot'),
            showlegend=True,
            hovertemplate=f'Lower Bound: {price_min:.2f}<extra></extra>'
        )
    )
    traces.append(
        go.Scatter(
            x=[price_max, price_max],
            y=[y_min - y_range * 0.1, y_max + y_range * 0.1],
            mode='lines',
            name='Upper Bound',
            line=dict(color='red', width=2, dash='dot'),
            showlegend=True,
            hovertemplate=f'Upper Bound: {price_max:.2f}<extra></extra>'
        )
    )
    
    # Add current price line
    if current_price:
        traces.append(
            go.Scatter(
                x=[current_price, current_price],
                y=[y_min - y_range * 0.1, y_max + y_range * 0.1],
                mode='lines',
                name='Current Price',
                line=dict(color='green', width=2, dash='dash'),
                hovertemplate=f'Current Price: {current_price:.2f}<extra></extra>'
            )
        )
    
    # Add combined value trace (optional)
    combined_values = [cv + fv for cv, fv in zip(current_values, fee_values)]
    traces.append(
        go.Scatter(
            x=prices,
            y=combined_values,
            mode='lines',
            name='Total Value (Position + Fees)',
            line=dict(color='#06A77D', width=2),
            opacity=0.7,
            hovertemplate='Price: %{x:.2f}<br>Total Value: %{y:.2f} USD<extra></extra>'
        )
    )
    
    pair = pos_data.get('Pair', 'Unknown')
    token_id = pos_data.get('TokenID', 'N/A')
    
    layout = go.Layout(
        title=f"Position Simulation - {pair} (TokenID: {token_id})",
        xaxis=dict(
            title=f'Price ({pair.split("/")[1]}/{pair.split("/")[0]})',
            showgrid=True,
            gridcolor='lightgray'
        ),
        yaxis=dict(
            title='Value (USD)',
            showgrid=True,
            gridcolor='lightgray'
        ),
        hovermode='x unified',
        template='plotly_white',
        height=600,
        legend=dict(x=0.02, y=0.98, bgcolor='rgba(255,255,255,0.8)'),
        margin=dict(l=60, r=20, t=60, b=60)
    )
    
    return go.Figure(data=traces, layout=layout)


# Initialize Dash app
app = dash.Dash(__name__)

app.layout = html.Div([
    html.H1(
        "Uniswap V3 Position Simulator",
        style={'textAlign': 'center', 'marginBottom': 30, 'color': '#2E86AB'}
    ),
    
    html.Div([
        html.Label(
            "Select Position:",
            style={'fontSize': 16, 'fontWeight': 'bold', 'marginRight': 10}
        ),
        dcc.Dropdown(
            id='position-dropdown',
            placeholder="Loading positions...",
            style={'width': '100%'}
        ),
    ], style={'width': '60%', 'margin': '0 auto', 'marginBottom': 30}),
    
    dcc.Loading(
        id="loading",
        type="default",
        children=dcc.Graph(id='simulation-chart')
    ),
    
    html.Div(
        id='position-info',
        style={
            'marginTop': 30,
            'textAlign': 'center',
            'padding': '20px',
            'backgroundColor': '#f8f9fa',
            'borderRadius': '10px',
            'width': '80%',
            'margin': '30px auto'
        }
    )
])


@app.callback(
    [Output('position-dropdown', 'options'),
     Output('position-dropdown', 'value')],
    Input('position-dropdown', 'id')
)
def load_positions(_):
    """Load positions and populate dropdown"""
    positions = load_positions_from_csv()
    if not positions:
        return [{'label': 'No positions found. Run query_v3_positions.py first.', 'value': -1}], None
    
    options = [
        {'label': f"#{p['TokenID']} - {p['Pair']} ({p['Fee']}) - {p.get('Status', 'Unknown')}", 'value': idx}
        for idx, p in enumerate(positions)
    ]
    
    return options, 0 if options else None


@app.callback(
    [Output('simulation-chart', 'figure'),
     Output('position-info', 'children')],
    Input('position-dropdown', 'value')
)
def update_chart(selected_idx):
    """Update chart based on selected position"""
    positions = load_positions_from_csv()
    
    if selected_idx is None or not positions or selected_idx < 0:
        empty_fig = go.Figure()
        empty_fig.update_layout(
            title="No position selected",
            xaxis_title="Price",
            yaxis_title="Value (USD)",
            height=600
        )
        return empty_fig, html.P("Please select a position from the dropdown above.")
    
    pos_data = positions[selected_idx]
    
    fig = create_simulator_chart(pos_data)
    
    # Create info display
    info = html.Div([
        html.H3(f"Position #{pos_data.get('TokenID', 'N/A')}", style={'color': '#2E86AB'}),
        html.Div([
            html.P([
                html.Strong("Pair: "), pos_data.get('Pair', 'N/A'), " | ",
                html.Strong("Fee: "), pos_data.get('Fee', 'N/A'), " | ",
                html.Strong("Status: "), pos_data.get('Status', 'N/A')
            ], style={'margin': '5px'}),
            html.P([
                html.Strong("Price Range: "), pos_data.get('Price Range', 'N/A'), " | ",
                html.Strong("Current Price: "), pos_data.get('Current Price', 'N/A')
            ], style={'margin': '5px'}),
            html.P([
                html.Strong("Current Value: "), pos_data.get('Current Value', 'N/A'), " | ",
                html.Strong("Current Amounts: "), pos_data.get('Current Amounts', 'N/A')
            ], style={'margin': '5px'}),
            html.P([
                html.Strong("Accumulated Fees: "), pos_data.get('Accumulated Fees', 'N/A'), " | ",
                html.Strong("Fees Value: "), pos_data.get('Fees Value', 'N/A')
            ], style={'margin': '5px'}),
        ])
    ])
    
    return fig, info


if __name__ == '__main__':
    port = 8053  # Changed to avoid conflict with other dashboards
    print("\n" + "="*60)
    print("Starting Uniswap V3 Position Simulator Dashboard")
    print("="*60)
    print(f"\nOpen http://127.0.0.1:{port} in your browser")
    print("\nMake sure you have:")
    print("  1. Run query_v3_positions.py at least once to generate positions.csv")
    print("  2. Installed required packages: pip install dash plotly pandas")
    print("\n" + "="*60 + "\n")
    app.run(debug=True, port=port, host='127.0.0.1')
