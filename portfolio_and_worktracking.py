import streamlit as st
import pandas as pd
import yfinance as yf
import sqlite3
from datetime import datetime

# Connect to SQLite database
conn = sqlite3.connect('portfolio.db')
c = conn.cursor()

# Create tables for storing client, transaction, employee, and task data
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

c.execute('''CREATE TABLE IF NOT EXISTS employees (
                employee_id INTEGER PRIMARY KEY AUTOINCREMENT,
                employee_name TEXT UNIQUE)''')

c.execute('''CREATE TABLE IF NOT EXISTS tasks (
                task_id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_name TEXT,
                description TEXT,
                assigned_to TEXT,
                added_date TEXT,
                deadline TEXT,
                status TEXT)''')

conn.commit()

# Function to calculate days pending
def calculate_days_pending(added_date):
    """Calculate the number of days since the task was added."""
    added_date = datetime.strptime(added_date, "%Y-%m-%d")
    current_date = datetime.now()
    days_pending = (current_date - added_date).days
    return days_pending

# Fetch current stock price using yfinance
def get_current_price(stock_symbol):
    try:
        ticker = yf.Ticker(stock_symbol + ".NS")  # NSE stocks require ".NS" suffix
        data = ticker.history(period="1d")
        return round(data['Close'][-1], 2)
    except Exception as e:
        return None

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
st.title("Portfolio and Work Tracking App")

# Sidebar for adding new clients and employees
st.sidebar.header("Add New Client / Employee")
client_name = st.sidebar.text_input("Client Name")
employee_name = st.sidebar.text_input("Employee Name")

if st.sidebar.button("Add Client"):
    try:
        c.execute(f"INSERT INTO clients (client_name) VALUES ('{client_name}')")
        conn.commit()
        st.sidebar.success(f"Client '{client_name}' added!")
    except sqlite3.IntegrityError:
        st.sidebar.error(f"Client '{client_name}' already exists!")

if st.sidebar.button("Add Employee"):
    try:
        c.execute(f"INSERT INTO employees (employee_name) VALUES ('{employee_name}')")
        conn.commit()
        st.sidebar.success(f"Employee '{employee_name}' added!")
    except sqlite3.IntegrityError:
        st.sidebar.error(f"Employee '{employee_name}' already exists!")

# Main Section
selected_section = st.selectbox("Choose a Section", ["Portfolio Tracking", "Work Tracking"])

# Portfolio Tracking Section
if selected_section == "Portfolio Tracking":
    st.header("Portfolio Tracking")

    # Select Client
    clients = pd.read_sql("SELECT client_name FROM clients", conn)['client_name'].tolist()
    selected_client = st.selectbox("Select Client", ["All"] + clients)

    # Filters for transactions
    stock_filter = st.text_input("Filter by Stock Symbol (e.g., RELIANCE)")
    transaction_type_filter = st.selectbox("Filter by Transaction Type", ["All", "Buy", "Sell"])

    # Display Transactions
    st.subheader("Add Transaction for Client")
    if selected_client != "All":
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

    transactions_query = "SELECT * FROM transactions"
    filters = []

    if selected_client != "All":
        filters.append(f"client_name = '{selected_client}'")
    if stock_filter:
        filters.append(f"stock_name LIKE '%{stock_filter}%'")
    if transaction_type_filter != "All":
        filters.append(f"transaction_type = '{transaction_type_filter}'")

    if filters:
        transactions_query += " WHERE " + " AND ".join(filters)

    transactions = pd.read_sql(transactions_query, conn)
    st.subheader("Filtered Transactions")
    st.dataframe(transactions)

    # Current Profits for Each Stock
    if selected_client != "All":
        st.subheader("Current Profits (Unrealized)")
        profit_df = calculate_current_profit(selected_client)
        if not profit_df.empty:
            st.dataframe(profit_df)
        else:
            st.write("No stocks held currently.")

        # Booked Profits
        st.subheader("Booked Profits")
        profit = calculate_booked_profit(selected_client)
        st.write(f"Total Booked Profit: ₹{profit}")

# Work Tracking Section
if selected_section == "Work Tracking":
    st.header("Work Tracking")

    # Filters for tasks
    employee_filter = st.selectbox("Filter by Assigned Employee", ["All"] + pd.read_sql("SELECT employee_name FROM employees", conn)['employee_name'].tolist())
    status_filter = st.selectbox("Filter by Task Status", ["All", "Pending", "In Progress", "Completed"])

    tasks_query = "SELECT * FROM tasks"
    task_filters = []

    if employee_filter != "All":
        task_filters.append(f"assigned_to = '{employee_filter}'")
    if status_filter != "All":
        task_filters.append(f"status = '{status_filter}'")

    if task_filters:
        tasks_query += " WHERE " + " AND ".join(task_filters)

    tasks = pd.read_sql(tasks_query, conn)
    if not tasks.empty:
        # Calculate "Days Pending" for each task
        tasks['Days Pending'] = tasks['added_date'].apply(calculate_days_pending)
        st.subheader("Filtered Tasks")
        st.dataframe(tasks)

        # Manage Tasks
        task_id = st.selectbox("Select Task ID", tasks['task_id'].tolist())
        selected_task = tasks[tasks['task_id'] == task_id]
        st.write(selected_task)

        # Update Task Status
        updated_status = st.selectbox("Update Status", ["Pending", "In Progress", "Completed"])
        if st.button("Update Task Status"):
            c.execute('UPDATE tasks SET status = ? WHERE task_id = ?', (updated_status, task_id))
            conn.commit()
            st.success("Task status updated successfully!")

        # Delete Task
        if st.button("Delete Task"):
            c.execute('DELETE FROM tasks WHERE task_id = ?', (task_id,))
            conn.commit()
            st.warning("Task deleted successfully!")
    else:
        st.write("No tasks found.")