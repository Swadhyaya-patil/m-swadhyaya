# # services.py
# from models import db, User, TradeRecommendation, Trade
# from angleone_integration import AngleOneClient
# from datetime import date
# import logging

# logger = logging.getLogger(__name__)

# def execute_trades_for_today():
#     today = date.today()
#     logger.info("Running trade executor...")

#     users = User.query.filter_by(is_active=True).all()
#     recommendations = TradeRecommendation.query.filter_by(reco_dt=today).all()

#     for reco in recommendations:
#         for user in users:
#             active_trade = Trade.query.filter_by(user_id=user.id, status="ongoing").first()
#             if active_trade:
#                 logger.info(f"Skipping user {user.client_id}: already in active trade")
#                 continue

#             broker = AngleOneClient(
#                 api_key=user.api_key,
#                 client_id=user.client_id,
#                 mpin=user.mpin,
#                 totp_token=user.totp_token
#             )
#             if not broker.login():
#                 logger.error(f"Login failed for user {user.client_id}")
#                 continue

#             success = broker.place_order(reco.script_name, reco.qty or 0, reco.purchase_price or 0)
#             if success:
#                 trade = Trade(
#                     user_id=user.id,
#                     trade_recommendation_id=reco.id,
#                     purchase_dt=today,
#                     purchase_price=reco.purchase_price or 0,
#                     qty=reco.qty or 0,
#                     tls=reco.tls,
#                     status="ongoing"
#                 )
#                 db.session.add(trade)
#                 db.session.commit()
#                 logger.info(f"Trade placed for user {user.client_id}")
#             else:
#                 logger.error(f"Failed to place trade for user {user.client_id}")

# services.py
from models import db, User, TradeRecommendation, Trade
from angleone_integration import AngleOneClient
from datetime import date
import logging
import math
from decimal import Decimal, ROUND_DOWN
import time

logger = logging.getLogger(__name__)

def execute_trades_for_recommendations():
    """
    For each active user (not admin):
        - Login once
        - For each active recommendation:
            - If user has not already taken this reco:
                - Calculate qty
                - Place order
                - Add trade record
    """
    logger.info("🚀 Starting trade execution process...")
    total_trades = 0

    # Step 1: Get all active users (excluding admins)
    active_users = User.query.filter(
        User.is_active == True,
        User.role != 'admin'
    ).all()
    if not active_users:
        logger.info("No active users found.")
        return

    logger.info(f"Found {len(active_users)} active users.")

    # Step 2: Get all trade recommendations with reco_dt set
    recos = TradeRecommendation.query.filter(
        TradeRecommendation.reco_dt.isnot(None)
    ).all()

    if not recos:
        logger.info("No trade recommendations found.")
        return

    logger.info(f"Found {len(recos)} trade recommendations to check.")

    # Step 3: For each user, login once and process all recos
    for user in active_users:
        logger.info(f"\n👤 Processing user {user.client_id}")

        # Login broker once
        broker = AngleOneClient(
            api_key=user.api_key,
            client_id=user.client_id,
            mpin=user.mpin,
            totp_token=user.totp_token
        )
        if not broker.login():
            logger.error(f"❌ Login failed for user {user.client_id}")
            continue

        # Step 3a: For each reco, check if user already has a trade and place if not
        for reco in recos:
            # Check if user already has trade for this reco
            existing_trade = Trade.query.filter_by(
                user_id=user.id,
                trade_recommendation_id=reco.id
            ).first()

            if existing_trade:
                logger.info(f"⚠️ User {user.client_id} already has trade for reco {reco.id}; skipping.")
                continue

            # Step 3b: Calculate qty based on user's capital
            capital = user.capital or Decimal('0')
            purchase_price = Decimal(str(reco.purchase_price or 1))
            per_trade_capital = capital / Decimal('10')

            if purchase_price == 0:
                logger.warning(f"⚠️ Purchase price is zero for reco {reco.id}; skipping.")
                continue

            qty = int((per_trade_capital / purchase_price).to_integral_value(rounding=ROUND_DOWN))

            if qty <= 0:
                logger.warning(f"⚠️ Calculated qty <= 0 for user {user.id} on reco {reco.id}; skipping.")
                continue

            # TODO: Chandu qty set to 1 for testing -- remove this when done 
            qty = 1
            # Step 3c: Place order
            response  = broker.place_order(
                script_name=reco.script_name,
                qty=qty,
                price=reco.purchase_price or 0
            )

            # Validate response properly
            if (
                isinstance(response, dict)
                and response.get("status") is True
                and response.get("message") == "SUCCESS"
            ):
                order_id = response.get("data", {}).get("orderid")  # get order ID safely
                unique_order_id = response.get("data", {}).get("uniqueorderid")

                # Record trade in DB
                new_trade = Trade(
                    user_id=user.id,
                    trade_recommendation_id=reco.id,
                    purchase_dt=date.today(),
                    purchase_price=reco.purchase_price or 0,
                    qty=qty,
                    tls=reco.tls,
                    status="ongoing",
                    script_name=reco.script_name,
                    # broker_order_id=order_id,              # optional: store broker order id
                    # broker_unique_order_id=unique_order_id  # optional: store unique order id
                )
                db.session.add(new_trade)
                db.session.commit()
                total_trades += 1
                logger.info(f"✅ Trade placed & saved for user {user.client_id} (qty={qty}) on reco {reco.id}, order_id={order_id}")
            else:
                logger.error(f"❌ Failed to place trade for user {user.client_id} on reco {reco.id}. Broker response: {response}")

    logger.info(f"🎉 Trade execution process complete. Total trades placed: {total_trades}")
    return total_trades


# def set_tsl_for_clients():

#     """
#     For each active user:
#     - Get current portfolio from broker
#     - Get user's ongoing trades
#     - For each ongoing trade:
#         - If script in portfolio and purchase_dt >= reco_dt:
#             - Get tls value from TradeRecommendation
#             - Call broker API to set/update trailing stop loss
#     """
#     logger.info("⚙️ Starting TSL setup process for all active users...")
#     set_TSL_internal()
#     active_users = User.query.filter(
#         User.is_active == True,
#         User.role != 'admin'
#     ).all()

#     if not active_users:
#         logger.info("No active users found.")
#         return

#     logger.info(f"Found {len(active_users)} active users.")

#     total_tsl_updates = 0

#     for user in active_users:
#         logger.info(f"\n👤 Processing user: {user.client_id}")

#         # Step 1: Login broker
#         broker = AngleOneClient(
#             api_key=user.api_key,
#             client_id=user.client_id,
#             mpin=user.mpin,
#             totp_token=user.totp_token
#         )
#         if not broker.login():
#             logger.error(f"❌ Login failed for user {user.client_id}")
#             continue

#         # Step 2: Get current portfolio from broker
#         portfolio_response = broker.get_holding()
#         print (f"portfolio_response ============>  {portfolio_response}")
#         if not portfolio_response or not portfolio_response.get('status'):
#             logger.warning(f"⚠️ Failed to get portfolio for user {user.client_id}; skipping.")
#             continue

#         portfolio_data = portfolio_response.get('data', [])
#         if not portfolio_data:
#             logger.info(f"⚠️ Empty portfolio for user {user.client_id}; skipping.")
#             print (f"⚠️ Empty portfolio for user {user.client_id}; skipping.")
#             continue

#         # Collect tradingsymbols into a set for quick lookup
#         portfolio_scripts = { item.get('tradingsymbol') for item in portfolio_data if item.get('tradingsymbol') }
#         logger.info(f"User portfolio scripts: {portfolio_scripts}")

#         # Step 3: Get user's ongoing trades
#         ongoing_trades = Trade.query.filter_by(
#             user_id=user.id,
#             status='ongoing'
#         ).all()
        
#         logger.info(f"Found {len(ongoing_trades)} ongoing trades for user {user.client_id}")
#         print (f"Found {len(ongoing_trades)} ongoing trades for user {user.client_id}")
#         for trade in ongoing_trades:
#             # Step 4: Check if trade script_name is in portfolio & purchase_dt >= reco_dt
#             if trade.script_name not in portfolio_scripts:
#                 logger.info(f"⏭️ Script {trade.script_name} not in portfolio; skipping.")
#                 continue

#             # Get the recommendation
#             reco = TradeRecommendation.query.filter_by(id=trade.trade_recommendation_id).first()
#             if not reco:
#                 logger.warning(f"⚠️ TradeRecommendation not found for trade {trade.id}; skipping.")
#                 continue

#             if trade.purchase_dt < reco.reco_dt:
#                 logger.info(f"⏭️ Trade purchase_dt {trade.purchase_dt} is before reco_dt {reco.reco_dt}; skipping.")
#                 continue

#             # Step 5: Get tls value and call broker API
#             tls_value = reco.tls
#             if not tls_value:
#                 logger.warning(f"⚠️ No TLS value set in reco {reco.id}; skipping.")
#                 continue

#             tsl_result = broker.place_TSL_order(script_name=trade.script_name, tsl_value=tls_value)

#             if tsl_result and tsl_result.get("status") == True:
#                 logger.info(f"✅ TSL set successfully for user {user.client_id} on script {trade.script_name}")
#                 total_tsl_updates += 1
#             else:
#                 logger.error(f"❌ Failed to set TSL for user {user.client_id} on script {trade.script_name}. Response: {tsl_result}")

#     logger.info(f"🎉 TSL setup process complete. Total TSL updates: {total_tsl_updates}")
#     return total_tsl_updates


# def set_TSL_internal():
#     """
#     For each active user:
#     - Get ongoing trades
#     - Check if the stock is in portfolio
#     - Get LTP from broker
#     - If LTP-based TSL > existing TSL in DB, update; else skip
#     """
#     logger.info("⚙️ Starting internal TSL updater...")

#     # Step 1: Get active users (excluding admin)
#     users = User.query.filter(
#         User.is_active == True,
#         User.role != 'admin'
#     ).all()

#     if not users:
#         logger.info("No active users found.")
#         return

#     total_updates = 0

#     for user in users:
#         logger.info(f"\n👤 Processing user {user.client_id}")

#         # Step 2: Login broker
#         broker = AngleOneClient(
#             api_key=user.api_key,
#             client_id=user.client_id,
#             mpin=user.mpin,
#             totp_token=user.totp_token
#         )
#         if not broker.login():
#             logger.error(f"❌ Login failed for user {user.client_id}")
#             continue

#         # Step 3: Get user's ongoing trades
#         ongoing_trades = Trade.query.filter_by(
#             user_id=user.id,
#             status='ongoing'
#         ).all()

#         if not ongoing_trades:
#             logger.info(f"No ongoing trades for user {user.client_id}.")
#             continue

#         # Step 4: Get user's live portfolio (symbols)
#         portfolio_response = broker.get_holding()
#         if not portfolio_response or not portfolio_response.get('status'):
#             logger.warning(f"⚠️ Failed to fetch portfolio for user {user.client_id}")
#             continue

#         portfolio_data = portfolio_response.get('data', [])
#         portfolio_symbols = { item.get('tradingsymbol') for item in portfolio_data if item.get('tradingsymbol') }
#         logger.info(f"User {user.client_id} portfolio symbols: {portfolio_symbols}")

#         for trade in ongoing_trades:
#             symbol_eq = f"{trade.script_name}-EQ"
#             print(f"symbol_eq ==> {symbol_eq}")

#             # Step 5: Check if the stock is in portfolio
#             if symbol_eq not in portfolio_symbols:
#                 logger.info(f"⏭️ Trade {trade.script_name} not in portfolio; skipping.")
#                 continue

#             # Step 6: Get LTP from broker
#             try:
#                 ltp_response = broker.angel_obj.ltpData(
#                     exchange='NSE',
#                     tradingsymbol=symbol_eq,
#                     symboltoken=broker.token_lookup(trade.script_name)
#                 )
#                 ltp = float(ltp_response['data']['ltp'])
#                 print(f"ltp ==> {ltp}")
#                 logger.info(f"LTP for {trade.script_name}: {ltp}")
#             except Exception as e:
#                 logger.error(f"❌ Failed to get LTP for {trade.script_name}: {str(e)}")
#                 continue

#             # Step 7: Calculate new TSL (e.g., 3% below LTP)
#             new_tsl = round(ltp * 0.97, 2)

#             print (f" new_tsl > trade.tls  Checking  {new_tsl} is is it greater than {trade.tls}")
#             # Step 8: If new_tsl > existing tls in DB, update
#             if new_tsl > (trade.tls or 0):
#                 logger.info(f"🔄 Updating TSL for trade {trade.id} from {trade.tls} to {new_tsl}")
#                 print(f"🔄 Updating TSL for trade {trade.id} from {trade.tls} to {new_tsl}")
#                 trade.tls = new_tsl
#                 db.session.commit()
#                 total_updates += 1
#             else:
#                 logger.info(f"✅ Existing TSL ({trade.tls}) is higher/equal; skipping update.")

#     logger.info(f"🎉 TSL updater finished. Total TSLs updated: {total_updates}")
#     return total_updates

# def set_tsl_for_clients(update_db=True, update_broker=True):
#     """
#     For each active user:
#     - Get ongoing trades
#     - Check if trade script is in user's live portfolio
#     - Get LTP from broker
#     - If new TSL > old TSL in DB:
#         - Update DB TSL (if update_db)
#         - Place broker TSL order (if update_broker)
#     """
#     logger.info(f"⚙️ Starting unified TSL updater: update_db={update_db}, update_broker={update_broker}")

#     active_users = User.query.filter(
#         User.is_active == True,
#         User.role != 'admin'
#     ).all()

#     if not active_users:
#         logger.info("No active users found.")
#         return

#     total_updates = 0

#     for user in active_users:
#         print(f"\n👤 TSL Processing user: {user.client_id}")
#         logger.info(f"\n👤 Processing user: {user.client_id}")

#         # Login broker
#         broker = AngleOneClient(
#             api_key=user.api_key,
#             client_id=user.client_id,
#             mpin=user.mpin,
#             totp_token=user.totp_token
#         )
#         if not broker.login():
#             logger.error(f"❌ Login failed for user {user.client_id}")
#             continue

#         # Get user's ongoing trades
#         ongoing_trades = Trade.query.filter_by(
#             user_id=user.id,
#             status='ongoing'
#         ).all()
#         if not ongoing_trades:
#             logger.info(f"No ongoing trades for user {user.client_id}")
#             continue

#         # Get portfolio
#         portfolio_response = broker.get_holding()
#         if not portfolio_response or not portfolio_response.get('status'):
#             logger.warning(f"⚠️ Failed to fetch portfolio for user {user.client_id}")
#             continue
#         portfolio_data = portfolio_response.get('data', [])
#         portfolio_symbols = { item.get('tradingsymbol') for item in portfolio_data if item.get('tradingsymbol') }

#         logger.info(f"User portfolio symbols: {portfolio_symbols}")

#         for trade in ongoing_trades:
#             symbol_eq = f"{trade.script_name}-EQ"

#             if symbol_eq not in portfolio_symbols:
#                 logger.info(f"⏭️ Trade {trade.script_name} not in portfolio; skipping.")
#                 continue

#             # Get LTP
#             try:
#                 ltp_response = broker.angel_obj.ltpData(
#                     exchange='NSE',
#                     tradingsymbol=symbol_eq,
#                     symboltoken=broker.token_lookup(trade.script_name)
#                 )
#                 ltp = float(ltp_response['data']['ltp'])
#                 logger.info(f"LTP for {trade.script_name}: {ltp}")
#             except Exception as e:
#                 logger.error(f"❌ Failed to get LTP for {trade.script_name}: {str(e)}")
#                 continue

#             # New TSL logic (3% below LTP)
#             new_tsl = round(ltp * 0.97, 2)

#             # Get reco (to compare with original tls if needed)
#             reco = TradeRecommendation.query.get(trade.trade_recommendation_id)

#             if not reco:
#                 logger.warning(f"⚠️ No recommendation found for trade {trade.id}; skipping broker TSL update.")
#                 continue

#             print(f"New TSL {new_tsl} & old {trade.tls} ")
#             # Only update if new TSL > existing TSL
#             if new_tsl > (trade.tls or 0):
#                 logger.info(f"🔄 New TSL ({new_tsl}) > old ({trade.tls}); updating.")

#                 if update_db:
#                     trade.tls = new_tsl
#                     db.session.commit()
#                     logger.info(f"✅ DB TSL updated for trade {trade.id}")

#                 if update_broker:
#                     # Place broker stop loss order using reco.tls or new_tsl
#                     tsl_value = new_tsl
#                     # tsl_result = broker.place_TSL_order(
#                     #     script_name=trade.script_name,
#                     #     # TODO: Chandu qty set to 1 for testing -- remove this when done 
#                     #     # qty=trade.qty,
#                     #     qty = 1,
#                     #     price=tsl_value,
#                     #     order_type='SELL'
#                     # )
#                     order_book = broker.get_order_book()
#                     order_id = None

#                     if order_book and isinstance(order_book, list):
#                         for order in order_book:
#                             if (
#                                 order.get('tradingsymbol') == symbol_eq
#                                 and order.get('ordertype') in ['STOPLOSS_LIMIT', 'SL', 'SL-M']
#                                 and order.get('status') in ['open', 'trigger pending']
#                             ):
#                                 order_id = order.get('orderid')
#                                 if order_id:
#                                     try:
#                                         cancel_result = broker.cancel_order(order_id)
#                                         logger.info(f"🗑️ Canceled existing TSL order {order_id} for {symbol_eq}")
#                                     except Exception as e:
#                                         logger.error(f"❌ Error cancelling order {order_id}: {str(e)}")
#                     else:
#                         logger.warning(f"⚠️ Order book empty or not a list for user {user.client_id}. Proceeding to place new TSL.")

#                     # ✅ Place new stoploss order regardless
#                     try:
#                         tsl_result = broker.place_TSL_order(
#                             script_name=trade.script_name,
#                             qty=1,
#                             price=new_tsl,
#                             order_type='SELL'
#                         )
#                         if tsl_result and tsl_result.get("status") == True:
#                             logger.info(f"✅ New TSL order placed for {trade.script_name} at {new_tsl}")
#                         else:
#                             logger.error(f"❌ Failed to place TSL for {trade.script_name}: {tsl_result}")
#                     except Exception as e:
#                         logger.error(f"❌ Exception placing TSL order for {trade.script_name}: {str(e)}")

#                 total_updates += 1
#             else:
#                 logger.info(f"✅ Existing TSL ({trade.tls}) is higher/equal; skipping update.")

#     logger.info(f"🎉 Unified TSL updater done. Total updates: {total_updates}")
#     return total_updates

def set_tsl_for_clients(update_db=True, update_broker=True):
    """
    For each active user:
    - Get ongoing trades
    - Check if trade script is in user's live portfolio
    - Get LTP from broker
    - Compute new TSL (3% below LTP)
    - If new TSL > old TSL → trail up
    - If new TSL < old TSL:
        - If LTP > old TSL → recreate missing broker TSL (broker cancels overnight)
        - If LTP < old TSL → exit trade at market (gap down)
    """
    logger.info(f"⚙️ Starting unified TSL updater: update_db={update_db}, update_broker={update_broker}")

    active_users = User.query.filter(
        User.is_active == True,
        User.role != 'admin'
    ).all()

    if not active_users:
        logger.info("No active users found.")
        return

    total_updates = 0

    for user in active_users:
        print(f"\n👤 TSL Processing user: {user.client_id}")
        logger.info(f"\n👤 Processing user: {user.client_id}")

        # Login broker
        broker = AngleOneClient(
            api_key=user.api_key,
            client_id=user.client_id,
            mpin=user.mpin,
            totp_token=user.totp_token
        )
        time.sleep(0.3)
        if not broker.login():
            logger.error(f"❌ Login failed for user {user.client_id}")
            continue

        # Get user's ongoing trades
        ongoing_trades = Trade.query.filter_by(
            user_id=user.id,
            status='ongoing'
        ).all()
        if not ongoing_trades:
            logger.info(f"No ongoing trades for user {user.client_id}")
            continue

        # Get portfolio
        portfolio_response = broker.get_holding()
        if not portfolio_response or not portfolio_response.get('status'):
            logger.warning(f"⚠️ Failed to fetch portfolio for user {user.client_id}")
            continue
        portfolio_data = portfolio_response.get('data', [])
        portfolio_symbols = { item.get('tradingsymbol') for item in portfolio_data if item.get('tradingsymbol') }

        logger.info(f"User portfolio symbols: {portfolio_symbols}")

        for trade in ongoing_trades:
            symbol_eq = f"{trade.script_name}-EQ"

            if symbol_eq not in portfolio_symbols:
                logger.info(f"⏭️ Trade {trade.script_name} not in portfolio; skipping.")
                continue

            # Get LTP
            try:
                time.sleep(0.3)
                ltp_response = broker.angel_obj.ltpData(
                    exchange='NSE',
                    tradingsymbol=symbol_eq,
                    symboltoken=broker.token_lookup(trade.script_name)
                )
                ltp = float(ltp_response['data']['ltp'])
                logger.info(f"LTP for {trade.script_name}: {ltp}")
            except Exception as e:
                logger.error(f"❌ Failed to get LTP for {trade.script_name}: {str(e)}")
                continue

            # Compute new TSL (3% below LTP)
            new_tsl = round(ltp * 0.97, 2)
            old_tsl = trade.tls or 0

            logger.info(f"{trade.script_name}: LTP={ltp}, new_tsl={new_tsl}, old_tsl={old_tsl}")

            # --- CASE 1: Trail Up (new TSL > old TSL)
            if new_tsl > old_tsl:
                logger.info(f"🔄 Trailing up {trade.script_name}: {old_tsl} → {new_tsl}")

                if update_db:
                    trade.tls = new_tsl
                    db.session.commit()
                    logger.info(f"✅ DB TSL updated for trade {trade.id}")

                if update_broker:
                    try:
                        # Cancel old stoploss order first
                        time.sleep(0.3)
                        order_book = broker.get_order_book()
                        if order_book and isinstance(order_book, list):
                            for order in order_book:
                                if (
                                    order.get('tradingsymbol') == symbol_eq and
                                    order.get('ordertype') in ['STOPLOSS_LIMIT', 'SL', 'SL-M'] and
                                    order.get('status') in ['open', 'trigger pending']
                                ):
                                    try:
                                        time.sleep(0.3)
                                        broker.cancel_order(order.get('orderid'))
                                        logger.info(f"🗑️ Canceled existing TSL order {order.get('orderid')} for {symbol_eq}")
                                    except Exception as e:
                                        logger.error(f"❌ Error cancelling order {order.get('orderid')}: {str(e)}")

                        # Place new TSL order
                        time.sleep(0.3)
                        tsl_result = broker.place_TSL_order(
                            script_name=trade.script_name,
                            qty=trade.qty or 1,
                            price=new_tsl,
                            order_type='SELL'
                        )
                        if tsl_result and tsl_result.get("status") == True:
                            logger.info(f"✅ New TSL placed for {trade.script_name} at {new_tsl}")
                        else:
                            logger.error(f"❌ Failed to place TSL for {trade.script_name}: {tsl_result}")

                    except Exception as e:
                        logger.error(f"❌ Exception placing TSL for {trade.script_name}: {str(e)}")

                total_updates += 1
                continue  # done for this trade

            # --- CASE 2: LTP above old TSL → Recreate missing overnight TSL
            if ltp > old_tsl and old_tsl > 0:
                logger.info(f"🟡 {trade.script_name}: LTP above old TSL ({old_tsl}). Checking broker orders...")

                try:
                    time.sleep(0.3)
                    order_book = broker.get_order_book()
                    tsl_exists = False
                    if order_book and isinstance(order_book, list):
                        for o in order_book:
                            if (
                                o.get('tradingsymbol') == symbol_eq and
                                o.get('ordertype') in ['STOPLOSS_LIMIT', 'SL', 'SL-M'] and
                                o.get('status') in ['open', 'trigger pending']
                            ):
                                trigger_price = float(o.get('triggerprice') or 0)
                                if abs(trigger_price - old_tsl) < 0.05:
                                    tsl_exists = True
                                    logger.info(f"✅ Existing TSL ({trigger_price}) found for {symbol_eq}")
                                    break

                    if not tsl_exists:
                        logger.info(f"⚠️ No TSL found for {symbol_eq}. Recreating at {old_tsl}")
                        time.sleep(0.3)
                        broker.place_TSL_order(
                            script_name=trade.script_name,
                            qty=trade.qty or 1,
                            price=old_tsl,
                            order_type='SELL'
                        )
                        logger.info(f"✅ Re-created TSL order for {symbol_eq} at {old_tsl}")

                except Exception as e:
                    logger.error(f"❌ Error checking/recreating TSL for {symbol_eq}: {str(e)}")
                continue  # done for this trade

            # --- CASE 3: Market opened below old TSL → Exit trade immediately
            if ltp <= old_tsl and old_tsl > 0:
                logger.warning(f"🚨 {trade.script_name}: LTP ({ltp}) below old TSL ({old_tsl}). Exiting position.")
                try:
                    time.sleep(0.3)
                    sell_result = broker.place_order(
                        script_name=trade.script_name,
                        qty=trade.qty or 1,
                        price=ltp,
                        order_type="SELL"

                    )
                    if sell_result and sell_result.get("status") == True:
                        trade.status = "exited"
                        trade.exit_price = ltp
                        db.session.commit()
                        logger.info(f"✅ Exited {trade.script_name} at {ltp}")
                    else:
                        logger.error(f"❌ Failed to exit {trade.script_name}: {sell_result}")
                except Exception as e:
                    logger.error(f"❌ Exception exiting {trade.script_name}: {str(e)}")
                continue  # done for this trade

            logger.info(f"✅ No TSL update needed for {trade.script_name}. Old TSL still valid.")

    logger.info(f"🎉 Unified TSL updater done. Total updates: {total_updates}")
    return total_updates
