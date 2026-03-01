# TODO - Once TSL hit, update user trades and reco
# TODO - add a page from where we can exit trades whenever we need.. target hit or something else.
# TODO = Function to generate TSL and keep updating on hourly basis
# TODO - add Telegram broadcast function
# TODO - Social Media integration needed??

from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from models import db, User, Trade, TradeRecommendation
from smartapi import SmartConnect
from smartapi.smartWebSocketV2 import SmartWebSocketV2
from pyotp import TOTP
from services import execute_trades_for_recommendations,set_tsl_for_clients
import math
import json
from flask import jsonify
from datetime import datetime, time
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from services import set_tsl_for_clients
from collections import defaultdict, OrderedDict
from angleone_integration import AngleOneClient
# import time

app = Flask(__name__)
app.secret_key = 'your_secret_key'  # change this to something strong

# Database config
# app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///mydatabase.db'  # update with your real DB URI
# app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql+pymysql://root:admin@localhost/bot_2025'


# app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

import os

db_user = os.getenv("DB_USER")
db_pass = os.getenv("DB_PASSWORD")
db_host = os.getenv("DB_HOST")
db_name = os.getenv("DB_NAME")

app.config['SQLALCHEMY_DATABASE_URI'] = (
    f"mysql+pymysql://{db_user}:{db_pass}@{db_host}/{db_name}"
)

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False


db.init_app(app)

# Create tables if they don't exist
with app.app_context():
    db.create_all()

# ----------------- Routes -----------------

# Landing page
# @app.route('/')
# def home():
#     return render_template('landing.html')

@app.route('/')
def home():
    return render_template('home.html')

# Register new user
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        name = request.form['name']
        pan = request.form['pan']
        mobile = request.form['mobile']
        broker = request.form['broker']
        api_key = request.form['api_key']
        client_id = request.form['client_id']
        mpin = request.form['mpin']
        totp_token = request.form['totp_token']
        capital = request.form['capital']

        existing_user = User.query.filter_by(username=username).first()
        if existing_user:
            flash('Username already exists. Please choose a different one.', 'error')
            return redirect(url_for('register'))

        hashed_pwd = generate_password_hash(password)

        new_user = User(
            username=username,
            password_hash=hashed_pwd,
            name=name,
            pan=pan,
            mobile=mobile,
            broker=broker,
            api_key=api_key,
            client_id=client_id,
            mpin=mpin,
            totp_token=totp_token,
            capital=capital
        )
        is_valid_user,actual_name = verify_user(api_key,client_id,mpin,totp_token)
        if(is_valid_user):
            new_user.name = actual_name
            db.session.add(new_user)
            db.session.commit()
            flash('Registration successful! Please login.', 'success')
            return redirect(url_for('login'))

    return render_template('register.html')

def verify_user(api_key,client_ID,mpin,totp ):
    clientName =""
    angel_obj = SmartConnect(api_key)
    # print("self.angel_obj {}".format(angel_obj))
    data = angel_obj.generateSession(client_ID,mpin,TOTP(totp).now())
    print("data {}".format(data))
    holdings=angel_obj.holding()
    print("+++++++++++++++++++++++++")
    print(holdings)
    print("+++++++++++++++++++++++++")
    # angel_WS_tocken = angel_obj.getfeedToken()
    # angel_WS_tocken = data["data"]["jwtToken"]
    # print("angel_WS_tocken {}".format(angel_WS_tocken))
    # angel_WS_Obj  = SmartWebSocketV2(data["data"]["jwtToken"], api_key, client_ID, angel_WS_tocken)
    # print("angel_WS_tocken {}".format(angel_WS_tocken))
    if data.get('status') == True and data.get('message') == 'SUCCESS':
        clientName = data.get('data', {}).get('name', '')
        print(f"client Name --> {clientName}")
        return True,clientName
    return False,clientName

# Login user
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password_hash, password):
            session['user_id'] = user.id
            session['username'] = user.username
            session['role'] = user.role
            flash('Logged in successfully!', 'success')
            return redirect(url_for('portfolio'))
        else:
            flash('Invalid username or password', 'error')
            return redirect(url_for('login'))

    return render_template('login.html')

# Logout
@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out.', 'info')
    return redirect(url_for('home'))

# Member landing page / portfolio
@app.route('/portfolio')
def portfolio():
    if 'user_id' not in session:
        flash('Please login first.', 'warning')
        return redirect(url_for('login'))

    user = User.query.get(session['user_id'])
    trades = Trade.query.filter_by(user_id=user.id).all()

    ongoing_trades = [t for t in trades if t.status == 'ongoing']
    exited_trades = [t for t in trades if t.status == 'exited']

    return render_template(
        'portfolio.html',
        user=user,
        ongoing_trades=ongoing_trades,
        exited_trades=exited_trades
    )


@app.route('/review_portfolio', methods=['POST'])
def review_portfolio():
    user_id = session.get('user_id')
    user = User.query.get(user_id)
    if not user:
        return render_template('portfolio.html', user=None, feedback="User not found.")

    api_key = user.api_key
    client_id = user.client_id
    mpin = user.mpin
    totp_token = user.totp_token

    angel_obj = SmartConnect(api_key)
    data = angel_obj.generateSession(client_id, mpin, TOTP(totp_token).now())
    portfolio = angel_obj.holding()
    portfolio_data = portfolio.get('data', [])

    symbols, invested, current_value, pnl = [], [], [], []
    total_invested, total_current, total_pnl = 0, 0, 0


    if portfolio_data:
        for item in portfolio_data:
            sym = item['tradingsymbol']
            qty = float(item['quantity'])
            avg_price = float(item['averageprice'])
            ltp = float(item['ltp'])
            inv = avg_price * qty
            cur = ltp * qty
            profit = cur - inv

            symbols.append(sym)
            invested.append(inv)
            current_value.append(cur)
            pnl.append(profit)

            total_invested += inv
            total_current += cur
            total_pnl += profit

        # Winners & Losers (Top 25% / Bottom 25%)
        sorted_data = sorted(portfolio_data, key=lambda x: x['pnlpercentage'], reverse=True)
        pnl_percentage = [float(item['pnlpercentage']) for item in portfolio_data]
        n = len(sorted_data)
        cut = max(1, math.ceil(n * 0.25))  # at least 1 stock

        top_stocks = sorted_data[:cut]
        bottom_stocks = sorted_data[-cut:]

        top_symbols = [x['tradingsymbol'] for x in top_stocks]
        top_pnl = [x['pnlpercentage'] for x in top_stocks]
        bottom_symbols = [x['tradingsymbol'] for x in bottom_stocks]
        bottom_pnl = [x['pnlpercentage'] for x in bottom_stocks]

        feedback = get_portfolio_feedback_from_llm(portfolio)
    else:
        feedback = "You don't seem to have any stocks"
        top_symbols, top_pnl, bottom_symbols, bottom_pnl = [], [], [], []

    return render_template(
        'portfolio.html',
        user=user,
        feedback=feedback,
        symbols=symbols,
        invested=invested,
        pnl=pnl,
        total_invested=total_invested,
        total_current=total_current,
        total_pnl=total_pnl,
        top_symbols=top_symbols,
        top_pnl=top_pnl,
        bottom_symbols=bottom_symbols,
        bottom_pnl=bottom_pnl,
        pnl_percentage=pnl_percentage
    )



@app.route("/live_market")
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return render_template("live_market.html")  # frontend will fetch data dynamically

import pytz

@app.route("/live_market/data")
def live_market_data():
    if 'user_id' not in session:
        return jsonify({"error": "not logged in"}), 401

    # check if current time is within market hours (IST)
    ist = pytz.timezone("Asia/Kolkata")
    now = datetime.now(ist).time()
    if not (time(9, 0) <= now <= time(15, 30)):
        return jsonify({"error": "Market Closed"}), 200

    user = db.session.get(User, session['user_id'])
    angel_obj = SmartConnect(user.api_key)
    angel_obj.generateSession(user.client_id, user.mpin, TOTP(user.totp_token).now())

    exchange_tokens = {"NSE": ["2885", "1333", "11536", "1594", "1394"]}
    exchange_tokens = top_five_invested_stocks()
    print(f"exchange_tokens => {exchange_tokens}")
    stocks_response = angel_obj.getMarketData(mode="FULL", exchangeTokens=exchange_tokens)

    fetched = stocks_response.get("data", {}).get("fetched", [])
    normalized = []

    for s in fetched:
        print(s)
        depth = s.get("depth", {})
        normalized.append({
            "symbol": s.get("tradingSymbol"),
            "ltp": s.get("ltp"),
            "percentChange": s.get("percentChange"),
            "tradeVolume": s.get("tradeVolume"),
            "weekLow": s.get("52WeekLow"),
            "weekHigh": s.get("52WeekHigh"),
            "lowerCircuit": s.get("lowerCircuit"),
            "upperCircuit": s.get("upperCircuit"),
            "buyDepth": depth.get("buy", []),
            "sellDepth": depth.get("sell", [])
        })
    print("++++++++++++++++++++++++++++++++++++++++++")
    print(normalized)
    print("++++++++++++++++++++++++++++++++++++++++++")
    return jsonify({"stocks": normalized})






#21-08-2025
# def review_portfolio():
#     user_id = session.get('user_id')  # however you track logged-in user
#     user = User.query.get(user_id)
#     print(user.api_key)
#     if not user:
#         return render_template('portfolio.html', user=None, feedback="User not found.")

#     # Step 1: Get API details
#     api_key = user.api_key
#     client_id = user.client_id
#     mpin = user.mpin
#     totp_token = user.totp_token

#     # Step 2: Connect to Angel One and get portfolio
#     angel_obj = SmartConnect(api_key)
#     data = angel_obj.generateSession(client_id,mpin,TOTP(totp_token).now())
#     # print("data {}".format(data))
#     portfolio=angel_obj.holding()
#     print(portfolio)
#     data = portfolio.get('data')
#     if isinstance(data, list) and len(data) > 0:
#         print("Data is a non-empty list")
#         feedback = get_portfolio_feedback_from_llm(portfolio)
#     else:
#         feedback = "You don't seems to have any stocks" #get_portfolio_feedback_from_llm(portfolio)
#         print("Data is empty or not a list")
#     # portfolio = get_portfolio_from_angel(api_key, client_id, mpin, totp_token)

#     # Step 3: Send portfolio to LLM for review
#     # feedback = get_portfolio_feedback_from_llm(portfolio)
#     # feedback=""

#     # Step 4: Return feedback to user (render on same page)
#     return render_template('portfolio.html', user=user, feedback=feedback,
#                            ongoing_trades=user.trades)



def get_portfolio_feedback_from_llm(portfolio):
    from openai import OpenAI
    import os
    from cerebras.cloud.sdk import Cerebras
    os.environ["CEREBRAS_API_KEY"] ="csk-f28twww3edpvyn4nfnr3etmyx9wf354fcjjm6cv4tnrfrmxe"
    client = Cerebras(api_key=os.environ.get("CEREBRAS_API_KEY"),)
    # prompt = "As a stock market(as a investor and trader) expert analyze following portfolio and suggest feedback to user. provide the feedback per stock basis like exit, hold or accoumalate. DO NOT provide any additional info/code etc"+str(portfolio.get("data"))
    prompt = (
    "You are a professional stock market analyst with expertise in both investing and trading. "
    "Analyze the following portfolio and provide concise, stock-specific feedback. "
    "For each stock:\n"
    "1. State the stock name clearly.\n"
    "2. Give a short rationale (3–4 sentences max) for fundamental analysis and (3–4 sentences max)technical analysis\n"
    "3. Conclude with one clear action: Exit, Hold, or Accumulate.\n\n"
    "Rules:\n"
    "- Keep the format consistent across all stocks.\n"
    "- Do not provide any additional commentary, explanations, or code.\n"
    "- Only respond with the structured analysis, nothing else.\n\n"
    "Use the following **Portfolio Data in JSON format** as the only factual source."
    "Compute everything else (percentages, P/L etc.) yourself."
    f"Portfolio: {portfolio.get('data')}"
)
    

    # prompt = (
    # "Act as a **veteran Indian equities & derivatives trader** and produce a highly detailed portfolio analysis and trade-plan."

    # "Use the following **Portfolio Data in JSON format** as the only factual source."
    # "Compute everything else (percentages, P/L etc.) yourself."

    # f"<PORTFOLIO_JSON> {portfolio.get('data')} </PORTFOLIO_JSON>"

    # "### Your Tasks"
    # "1. **Portfolio Snapshot Table**  "
    # "   *Show Symbol, Quantity (filled), Avg-Price, LTP, Realised P/L (₹), % P/L, Current Exposure.*  "
    # "   *Compute net overall P&L and highlight maximum drawdown.*"

    # "2. **Risk & Concentration Analysis**  "
    # "   *Sector exposure, liquidity, delivery vs. derivatives, any concentration risk.*"

    # "3. **Advanced Technical View**  "
    # "   *Use plausible but clearly marked technicals (20- & 50-day SMA, RSI-14, MACD 12/26/9) as if from yesterday’s daily charts.*  "
    # "   *Provide Support/Resistance, trend bias.*"

    # "4. **Actionable Trade Recommendations**  "
    # "   *For each script: fresh trade idea, entry/add-on zone, stop-loss, targets, and expected Risk:Reward.*"

    # "5. **Derivatives Opportunities**  "
    # "   *Options or futures structures (buy/sell calls/puts, spreads, or NIFTY hedge) with reasoning and approximate implied vol.*"

    # "6. **Strategic Hedging & Pair-Trades**  "
    # "   *Beta hedges, correlated sectors, or pairs to reduce portfolio risk.*"

    # "7. **Capital Re-allocation Guidance**  "
    # "   *Where to redeploy freed capital, how much cash buffer to keep, and which new sectors/stocks to watch.*"

    # "Format the response with:"
    # "* clear markdown tables,"
    # "* crisp bullet-points,"
    # "* and an “Immediate Action Checklist” at the end."

    # "Be concise but cover all 7 sections thoroughly."
    # )

    chat_completion = client.chat.completions.create(messages=[{"role": "user", "content": prompt,}],model="llama3.1-8b",)

    print(chat_completion)
    content = chat_completion.choices[0].message.content

    print("Extracted content:\n")
    print(content)
    return content

# Analyze existing portfolio (dummy for now)
@app.route('/analyze')
def analyze():
    if 'user_id' not in session:
        flash('Please login first.', 'warning')
        return redirect(url_for('login'))

    # Later you can add real analysis logic
    flash('Portfolio analysis completed. (Mock)', 'info')
    return redirect(url_for('portfolio'))

@app.route('/dashboard')
def member_dashboard():
    return redirect(url_for('portfolio'))


@app.route('/risk-profile', methods=['GET', 'POST'])
# @login_required
def risk_profile():
    # Ensure only 'user' role can access (optional)
    if 'user_id' not in session:
        flash('Please login first.', 'warning')
        return redirect(url_for('login'))

    if request.method == 'POST':
        # Collect answers
        answers = {
            "horizon": int(request.form.get("horizon")),
            "goal": int(request.form.get("goal")),
            "volatility": int(request.form.get("volatility")),
            "risk": int(request.form.get("risk")),
            "allocation": int(request.form.get("allocation"))
        }

        # Calculate total score
        total_score = sum(answers.values())

        # Map score → category
        if total_score <= 8:
            profile = "risk_averse"
        elif total_score <= 11:
            profile = "conservative"
        elif total_score <= 14:
            profile = "balanced"
        elif total_score <= 16:
            profile = "growth"
        else:
            profile = "aggressive"

        # Save only to the logged-in user's record
        # user.risk_profile = profile
        # db.session.commit()

        flash(f"✅ Your risk profile has been set to: {profile.replace('_', ' ').title()}", "success")
        return redirect(url_for('portfolio'))

    return render_template("risk_profile.html", current_profile="")#user.risk_profile)


# app.py (add these imports at top if missing)
from flask import Flask, render_template, request, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash, check_password_hash
from models import db, User, TradeRecommendation, Trade
from datetime import datetime

# Admin login page
@app.route('/admin', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        admin = User.query.filter_by(username=username, role='admin').first()
        if admin and check_password_hash(admin.password_hash, password):
            session['admin_id'] = admin.id
            return redirect(url_for('admin_dashboard'))
        else:
            flash('Invalid credentials or not an admin')
    return render_template('admin_login.html')

# Admin dashboard
@app.route('/admin/dashboard')
def admin_dashboard():
    if 'admin_id' not in session:
        return redirect(url_for('admin_login'))
    trades = Trade.query.all()
    return render_template('admin_dashboard.html', trades=trades)

# Add recommendation
from datetime import datetime

@app.route('/admin/add_trade', methods=['GET', 'POST'])
def add_trade():
    if 'admin_id' not in session:
        return redirect(url_for('admin_login'))
    if request.method == 'POST':
        script_name = request.form['script_name']
        reco_dt = datetime.strptime(request.form['reco_dt'], '%Y-%m-%d')
        purchase_price = float(request.form['purchase_price'])
        reasoning = request.form['reasoning']
        tls = float(request.form['tls'])
        recommendation = TradeRecommendation(
            script_name=script_name,
            reco_dt=reco_dt,
            purchase_price=purchase_price,
            reasoning=reasoning,
            tls=tls
        )
        db.session.add(recommendation)
        db.session.commit()
        flash('Trade recommendation added successfully')
        return redirect(url_for('admin_dashboard'))
    current_date = datetime.utcnow().strftime('%Y-%m-%d')
    return render_template('add_trade.html', current_date=current_date)


# # Execute trade for all users
# @app.route('/admin/execute_trade')
# def execute_trade():
#     if 'admin_id' not in session:
#         return redirect(url_for('admin_login'))

#     latest_reco = TradeRecommendation.query.order_by(TradeRecommendation.id.desc()).first()
#     if latest_reco:
#         users = User.query.filter_by(role='user').all()
#         for user in users:
#             trade = Trade(
#                 user_id=user.id,
#                 script_name = latest_reco.script_name,
#                 trade_recommendation_id=latest_reco.id,
#                 purchase_dt=datetime.utcnow(),
#                 purchase_price=latest_reco.purchase_price or 0.0,
#                 qty=latest_reco.qty or 1,
#                 tls=latest_reco.tls,
#                 status='ongoing'
#             )
#             db.session.add(trade)
#         db.session.commit()
#         flash(f'Executed trade for {len(users)} users.')
#     else:
#         flash('No trade recommendation to execute.')
#     return redirect(url_for('admin_dashboard'))
# Execute trade for all users
@app.route('/admin/execute_trade')
def execute_trade():
    if 'admin_id' not in session:
        return redirect(url_for('admin_login'))

    # Call the main trade execution function
    count = execute_trades_for_recommendations()

    if count and count > 0:
        print(f'Successfully executed trades for {count} users.')
        flash(f'Successfully executed trades for {count} users.')        
    else:
        print('No trades were executed. Either no new recommendations, holidays/weekends, or all users already have active trades.')
        flash('No trades were executed. Either no new recommendations, holidays/weekends, or all users already have active trades.')

    return redirect(url_for('admin_dashboard'))

@app.route('/admin/set_TSL')
def set_TSL():
    if 'admin_id' not in session:
        return redirect(url_for('admin_login'))

    # Call the main trade execution function
    count = set_tsl_for_clients()

    if count and count > 0:
        print(f'Successfully executed trades for {count} users.')
        flash(f'Successfully executed trades for {count} users.')        
    else:
        print('No set_TSL. no trades ongoing or executed for users')
        flash('No set_TSL. no trades ongoing or executed for users')

    return redirect(url_for('admin_dashboard'))


# Admin logout
@app.route('/admin/logout')
def admin_logout():
    session.pop('admin_id', None)
    return redirect(url_for('admin_login'))

# @app.route("/public/recommendations")
# def public_recommendations():
#     recos = TradeRecommendation.query.all()
#     trades = Trade.query.all()

#     performance_data = []
#     cumulative_data = []
#     monthly_values = OrderedDict()
#     cumulative_value = 100.0  # base index = 100
#     monthly_returns = OrderedDict()

#     user_id = session.get('user_id')
#     user = User.query.get(user_id)
#     if not user:
#         return render_template('portfolio.html', user=None, feedback="User not found.")

#     client = AngleOneClient(
#         api_key=user.api_key,
#         client_id=user.client_id,
#         mpin=user.mpin,
#         totp_token=user.totp_token
#     )
#     client.login()

#     # --- Sort trades by date (oldest first)
#     trades = sorted(trades, key=lambda t: t.exit_dt or datetime.utcnow().date())

#     for trade in trades:
#         if not trade.purchase_price:
#             continue

#         entry_dt = trade.purchase_dt or trade.trade_recommendation.reco_dt
#         exit_dt = trade.exit_dt or datetime.utcnow().date()

#         # --- Get exit or LTP for ongoing trades
#         if trade.status == "exited" and trade.exit_price:
#             effective_exit_price = trade.exit_price
#         else:
#             try:
#                 ltp_data = client.ltpData(trade.script_name)
#                 effective_exit_price = ltp_data["data"]["ltp"]
#             except Exception as e:
#                 print(f"⚠️ Failed to fetch LTP for {trade.script_name}: {e}")
#                 effective_exit_price = trade.purchase_price

#         # --- Calculate trade return
#         pct_return = ((effective_exit_price - trade.purchase_price) / trade.purchase_price) * 100
#         trade_duration = (exit_dt - entry_dt).days if entry_dt and exit_dt else 0

#         performance_data.append({
#             "script": trade.script_name,
#             "reco_date": entry_dt,
#             "purchase_price": round(trade.purchase_price, 2),
#             "exit_price": round(effective_exit_price, 2),
#             "status": trade.status,
#             "pnl_pct": round(pct_return, 2),
#             "duration": trade_duration,
#             "reasoning": trade.trade_recommendation.reasoning if trade.trade_recommendation else "-"
#         })

#         # --- Update cumulative portfolio value
#         cumulative_value *= (1 + pct_return / 100)
#         month_key = exit_dt.strftime("%Y-%m")
#         monthly_values[month_key] = cumulative_value  # latest cumulative per month

#     # --- Convert cumulative values to monthly % changes
#     prev_val = None
#     for month, val in monthly_values.items():
#         if prev_val is None:
#             monthly_returns[month] = 0
#         else:
#             monthly_returns[month] = round(((val - prev_val) / prev_val) * 100, 2)
#         prev_val = val

#     # --- Prepare chart-friendly data
#     cumulative_data = [{"date": k, "cumulative": round(v, 2)} for k, v in monthly_values.items()]
#     monthly_summary = [{"month": k, "return": v} for k, v in monthly_returns.items()]

#     print(f"cumulative_data {cumulative_data}")
#     print(f"monthly_summary {monthly_summary}")

#     return render_template(
#         "public_recommendations.html",
#         recos=performance_data,
#         cumulative_data=cumulative_data,
#         monthly_summary=monthly_summary
#     )

@app.route("/public/recommendations")
def public_recommendations():
    trades = Trade.query.all()
    if not trades:
        return render_template(
            "public_recommendations.html",
            completed_data=[],
            ongoing_data=[],
            recos=[]
        )

    completed_data = []
    ongoing_data = []
    performance_data = []

    user_id = session.get('user_id')
    user = User.query.get(user_id)
    if not user:
        return render_template('portfolio.html', user=None, feedback="User not found.")

    client = AngleOneClient(
        api_key=user.api_key,
        client_id=user.client_id,
        mpin=user.mpin,
        totp_token=user.totp_token
    )
    client.login()
    # # client = None
    # try:
    #     client = AngleOneClient()
    #     client.login()
    # except Exception as e:
    #     print(f"⚠️ Could not init AngelOne client: {e}")
    #     client = None

    for trade in trades:
        if not trade.purchase_price:
            continue

        purchase_price = float(trade.purchase_price)
        script = trade.script_name

        # --- Completed trades
        if trade.status.lower() == "exited" and trade.exit_price:
            exit_price = float(trade.exit_price)
            ret = ((exit_price - purchase_price) / purchase_price) * 100
            completed_data.append({"symbol": script, "return": round(ret, 2)})
            performance_data.append({
                "script": script,
                "purchase_price": purchase_price,
                "exit_price": exit_price,
                "status": "Completed",
                "pnl_pct": round(ret, 2)
            })
        else:
            # --- Ongoing trades
            ltp = purchase_price
            if client:
                try:
                    time.sleep(0.3)
                    resp = client.ltpData(script)
                    ltp = float(resp["data"]["ltp"])
                except Exception as e:
                    print(f"⚠️ LTP fetch failed for {script}: {e}")

            ret = ((ltp - purchase_price) / purchase_price) * 100
            ongoing_data.append({"symbol": script, "return": round(ret, 2)})
            performance_data.append({
                "script": script,
                "purchase_price": purchase_price,
                "exit_price": ltp,
                "status": "Ongoing",
                "pnl_pct": round(ret, 2)
            })

    return render_template(
        "public_recommendations.html",
        recos=performance_data,
        completed_data=completed_data,
        ongoing_data=ongoing_data
    )

def start_scheduler(app):
    scheduler = BackgroundScheduler()

    # ✅ Wrap the actual job in a function that runs inside Flask's app context
    def run_set_tsl_for_clients():
        from services import set_tsl_for_clients
        with app.app_context():
            set_tsl_for_clients()

    # --- Morning Job (09:15 AM)
    morning_trigger = CronTrigger(
        day_of_week='mon-fri',
        hour=9,
        minute=15,
        timezone='Asia/Kolkata'
    )
    scheduler.add_job(
        func=run_set_tsl_for_clients,
        trigger=morning_trigger,
        id='morning_tsl_update',
        replace_existing=True
    )

    # --- Afternoon Job (14:00 PM)
    afternoon_trigger = CronTrigger(
        day_of_week='mon-fri',
        hour=14,
        minute=00,
        timezone='Asia/Kolkata'
    )
    scheduler.add_job(
        func=run_set_tsl_for_clients,
        trigger=afternoon_trigger,
        id='afternoon_tsl_update',
        replace_existing=True
    )

    scheduler.start()
    print("✅ Scheduler started: Mon–Fri at 09:15 AM & 02:00 PM IST")


def top_five_invested_stocks():
    import time
    user_id = session.get('user_id')
    user = User.query.get(user_id)
    default_exchange_tokens = {"NSE": ["2885", "1333", "11536", "1594", "1394"]}
    if not user:
        return default_exchange_tokens

    api_key = user.api_key
    client_id = user.client_id
    mpin = user.mpin
    totp_token = user.totp_token
    time.sleep(0.3)
    angel_obj = SmartConnect(api_key)
    angel_obj.generateSession(client_id, mpin, TOTP(totp_token).now())
    time.sleep(0.3)
    portfolio = angel_obj.holding()
    portfolio_data = portfolio.get('data', [])

    if not portfolio_data:
        return default_exchange_tokens

    # Compute invested amount for each stock
    for item in portfolio_data:
        qty = float(item.get('quantity', 0))
        avg_price = float(item.get('averageprice', 0))
        item['invested_value'] = avg_price * qty

    # Sort by invested value (descending) and take top 5
    top_invested = sorted(portfolio_data, key=lambda x: x['invested_value'], reverse=True)[:5]

    # Extract their script/symbol codes
    top_codes = [
        item.get('symboltoken') or item.get('script_code')
        for item in top_invested
        if item.get('symboltoken') or item.get('script_code')
    ]

    # Return in required format
    exchange_tokens = {"NSE": top_codes}
    return exchange_tokens

# ----------------- End Routes -----------------

if __name__ == '__main__':
    
    from app import app  # if not already imported
    start_scheduler(app)
    # start_scheduler()

    # app.run(debug=True)
    app.run(host='0.0.0.0', port=80,debug=True)
