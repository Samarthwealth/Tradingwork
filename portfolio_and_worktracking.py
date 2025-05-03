import streamlit as st
import pandas as pd
import yfinance as yf
import sqlite3

# Connect to SQLite database
conn = sqlite3.connect('portfolio.db')
c = conn.cursor()

# Create tables
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

# Function to fetch current stock price
def get_current_price(stock_symbol):
    try:
        ticker = yf.Ticker(stock_symbol + ".NS")
        data = ticker.history(period="1d")
        return round(data['Close'][-1], 2)
    except Exception:
        return None

# Function to calculate realized profit/loss
def calculate_realized_profit(client_name):
    transactions = pd.read_sql(f"SELECT * FROM transactions WHERE client_name = '{client_name}'", conn)
    if transactions.empty:
        return 0

    total_realized_profit = 0
    for _, row in transactions.iterrows():
        if row['transaction_type'] == 'Sell':
            buy_transactions = transactions[
                (transactions['stock_name'] == row['stock_name']) &
                (transactions['transaction_type'] == 'Buy')
            ]
            if not buy_transactions.empty:
                avg_buy_price = buy_transactions['price'].mean()
                total_realized_profit += (row['price'] - avg_buy_price) * row['quantity']

    return round(total_realized_profit, 2)

# Function to calculate unrealized profit/loss
def calculate_unrealized_profit(client_name):
    transactions = pd.read_sql(f"SELECT * FROM transactions WHERE client_name = '{client_name}'", conn)
    if transactions.empty:
        return pd.DataFrame()

    profit_data = []
    for stock in transactions['stock_name'].unique():
        stock_transactions = transactions[transactions['stock_name'] == stock]
        buy_transactions = stock_transactions[stock_transactions['transaction_type'] == 'Buy']
        total_quantity = buy_transactions['quantity'].sum()

        if total_quantity > 0:
            avg_buy_price = (buy_transactions['quantity'] * buy_transactions['price']).sum() / total_quantity
            current_price = get_current_price(stock)

            if current_price is not None:
                unrealized_profit = (current_price - avg_buy_price) * total_quantity
                profit_data.append({
                    "Stock Name": stock,
                    "Average Buy Price": round(avg_buy_price, 2),
                    "Current Market Price": round(current_price, 2),
                    "Quantity Held": total_quantity,
                    "Unrealized Profit/Loss": round(unrealized_profit, 2)
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
    # Update Client Name
    st.sidebar.header("Update Client Name")
    new_client_name = st.sidebar.text_input("New Client Name")
    if st.sidebar.button("Update Client"):
        try:
            c.execute(f"UPDATE clients SET client_name = '{new_client_name}' WHERE client_name = '{selected_client}'")
            c.execute(f"UPDATE transactions SET client_name = '{new_client_name}' WHERE client_name = '{selected_client}'")
            conn.commit()
            st.sidebar.success(f"Client name updated from '{selected_client}' to '{new_client_name}'!")
        except sqlite3.IntegrityError:
            st.sidebar.error(f"Client '{new_client_name}' already exists!")

    # Delete Client
    st.sidebar.header("Delete Client")
    if st.sidebar.button("Delete Client"):
        c.execute(f"DELETE FROM clients WHERE client_name = '{selected_client}'")
        c.execute(f"DELETE FROM transactions WHERE client_name = '{selected_client}'")
        conn.commit()
        st.sidebar.success(f"Client '{selected_client}' has been deleted!")

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

    # Transaction History
    transactions = pd.read_sql(f"SELECT * FROM transactions WHERE client_name = '{selected_client}'", conn)
    st.subheader("Transaction History")
    st.dataframe(transactions)

    # Update Transaction
    st.subheader("Update Transaction")
    if not transactions.empty:
        selected_transaction_id = st.selectbox("Select Transaction ID", transactions["transaction_id"].tolist())
        new_price = st.number_input("New Price per Unit", min_value=0.0)
        new_quantity = st.number_input("New Quantity", min_value=1)

        if st.button("Update Transaction"):
            c.execute(f"UPDATE transactions SET price = {new_price}, quantity = {new_quantity} WHERE transaction_id = {selected_transaction_id}")
            conn.commit()
            st.success(f"Transaction ID {selected_transaction_id} updated!")

    # Delete Transaction
    st.subheader("Delete Transaction")
    if not transactions.empty:
        selected_transaction_id_delete = st.selectbox("Select Transaction ID to Delete", transactions["transaction_id"].tolist())

        if st.button("Delete Transaction"):
            c.execute(f"DELETE FROM transactions WHERE transaction_id = {selected_transaction_id_delete}")
            conn.commit()
            st.success(f"Transaction ID {selected_transaction_id_delete} deleted!")

    # Portfolio Insights
    st.subheader("Portfolio Insights")

    # Realized Profit/Loss
    realized_profit = calculate_realized_profit(selected_client)
    st.write(f"**Realized Profit/Loss:** ₹{realized_profit:,.2f}")

    # Unrealized Profit/Loss
    unrealized_profit_df = calculate_unrealized_profit(selected_client)
    if not unrealized_profit_df.empty:
        st.subheader("Unrealized Profit/Loss")
        st.dataframe(unrealized_profit_df)
    else:
        st.write("No stocks held currently.")
