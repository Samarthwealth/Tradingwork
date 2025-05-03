import streamlit as st
import pandas as pd
import yfinance as yf
import sqlite3

# Connect to SQLite database
conn = sqlite3.connect('portfolio.db')
c = conn.cursor()

# Create tables for storing client and transaction data
c.execute('''CREATE TABLE IF NOT EXISTS clients (
                client_id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_name TEXT UNIQUE)''')

c.execute('''CREATE TABLE IF NOT EXISTS transactions (
                transaction_id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_name TEXT,
                stock_name TEXT,
                transaction_type TEXT,
                quantity INTEGER,
                price REAL,
                date TEXT)''')

conn.commit()

# Fetch current stock price using yfinance
def get_current_price(stock_symbol):
    try:
        ticker = yf.Ticker(stock_symbol + ".NS")  # NSE stocks require ".NS" suffix
        data = ticker.history(period="1d")
        return round(data['Close'][-1], 2)
    except Exception:
        return None

# Calculate deployed amount for a client
def calculate_deployed_amount(client_name):
    transactions = pd.read_sql(f"SELECT * FROM transactions WHERE client_name = '{client_name}'", conn)
    if transactions.empty:
        return 0

    buy_transactions = transactions[transactions['transaction_type'] == 'Buy']
    deployed_amount = (buy_transactions['quantity'] * buy_transactions['price']).sum()
    return deployed_amount

# Calculate booked profits for a client
def calculate_booked_profit(client_name):
    transactions = pd.read_sql(f"SELECT * FROM transactions WHERE client_name = '{client_name}'", conn)
    if transactions.empty:
        return 0

    total_profit = 0
    for _, row in transactions.iterrows():
        if row['transaction_type'] == 'Sell':
            buy_transactions = transactions[
                (transactions['stock_name'] == row['stock_name']) &
                (transactions['transaction_type'] == 'Buy')
            ]
            if not buy_transactions.empty:
                avg_buy_price = buy_transactions['price'].mean()
                total_profit += (row['price'] - avg_buy_price) * row['quantity']
    return total_profit

# Calculate current profits (unrealized) for each stock
def calculate_current_profit(client_name):
    transactions = pd.read_sql(f"SELECT * FROM transactions WHERE client_name = '{client_name}'", conn)
    if transactions.empty:
        return pd.DataFrame()

    profit_data = []
    for stock in transactions['stock_name'].unique():
        stock_transactions = transactions[transactions['stock_name'] == stock]

        # Filter only "Buy" transactions to calculate average buy price
        buy_transactions = stock_transactions[stock_transactions['transaction_type'] == 'Buy']
        total_quantity = buy_transactions['quantity'].sum()

        if total_quantity > 0:
            avg_buy_price = (buy_transactions['quantity'] * buy_transactions['price']).sum() / total_quantity
            total_quantity_held = total_quantity

            # Fetch current market price using yfinance
            current_price = get_current_price(stock)
            if current_price is not None:
                unrealized_profit = (current_price - avg_buy_price) * total_quantity_held
                profit_data.append({
                    "Stock Name": stock,
                    "Average Buy Price": round(avg_buy_price, 2),
                    "Current Market Price": round(current_price, 2),
                    "Quantity Held": total_quantity_held,
                    "Unrealized Profit": round(unrealized_profit, 2)
                })

    return pd.DataFrame(profit_data)

# Streamlit App
st.title("Stock Portfolio Tracking App")

# Add New Client
st.sidebar.header("Add New Client")
client_name = st.sidebar.text_input("Client Name")
if st.sidebar.button("Add Client"):
    try:
        c.execute(f"INSERT INTO clients (client_name) VALUES ('{client_name}')")
        conn.commit()
        st.sidebar.success(f"Client '{client_name}' added!")
    except sqlite3.IntegrityError:
        st.sidebar.error(f"Client '{client_name}' already exists!")

# Select Client
clients = pd.read_sql("SELECT client_name FROM clients", conn)['client_name'].tolist()
selected_client = st.selectbox("Select Client", clients)

if selected_client:
    # Add Transaction
    st.header(f"Add Transaction for {selected_client}")
    stock_name = st.text_input("Stock Symbol (e.g., RELIANCE)")
    transaction_type = st.radio("Transaction Type", ["Buy", "Sell"])
    quantity = st.number_input("Quantity", min_value=1)
    price = st.number_input("Price per Unit", min_value=0.0)
    date = st.date_input("Transaction Date")
    if st.button("Add Transaction"):
        c.execute('''INSERT INTO transactions (client_name, stock_name, transaction_type, quantity, price, date)
                     VALUES (?, ?, ?, ?, ?, ?)''',
                  (selected_client, stock_name, transaction_type, quantity, price, date))
        conn.commit()
        st.success(f"{transaction_type} entry added for {stock_name}!")

    # Portfolio Overview
    st.header(f"Portfolio Overview for {selected_client}")

    # Display the transaction table
    transactions = pd.read_sql(f"SELECT * FROM transactions WHERE client_name = '{selected_client}'", conn)
    st.subheader("Transaction History")
    st.dataframe(transactions)

    # Summary Insights
    st.subheader("Portfolio Insights")
    deployed_amount = calculate_deployed_amount(selected_client)
    unrealized_profit = calculate_current_profit(selected_client)['Unrealized Profit'].sum() if not calculate_current_profit(selected_client).empty else 0
    remaining_amount = deployed_amount + unrealized_profit

    st.write(f"**Deployed Amount:** ₹{deployed_amount:,.2f}")
    st.write(f"**Unrealized Profit/Loss:** ₹{unrealized_profit:,.2f}")
    st.write(f"**Amount Remaining:** ₹{remaining_amount:,.2f}")

    # Booked Profits
    st.subheader("Booked Profits")
    profit = calculate_booked_profit(selected_client)
    st.write(f"Total Booked Profit: ₹{profit}")

    # Current Profits for Each Stock
    st.subheader("Current Profits (Unrealized)")
    profit_df = calculate_current_profit(selected_client)
    if not profit_df.empty:
        st.dataframe(profit_df)
    else:
        st.write("No stocks held currently.")
