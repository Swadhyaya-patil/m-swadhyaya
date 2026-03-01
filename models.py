# models.py
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

class User(db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=True)
    role = db.Column(db.Enum('user', 'admin'), default='user')
    name = db.Column(db.String(100))
    pan = db.Column(db.String(20))
    mobile = db.Column(db.String(15))
    broker = db.Column(db.String(50))
    api_key = db.Column(db.String(100))
    client_id = db.Column(db.String(50))
    mpin = db.Column(db.String(20))
    totp_token = db.Column(db.String(50))
    capital = db.Column(db.Numeric(12, 2))
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    trades = db.relationship('Trade', back_populates='user')

class TradeRecommendation(db.Model):
    __tablename__ = 'trade_recommendations'

    id = db.Column(db.Integer, primary_key=True)
    script_name = db.Column(db.String(100))
    reco_dt = db.Column(db.Date)
    purchase_dt = db.Column(db.Date, nullable=True)
    purchase_price = db.Column(db.Float, nullable=True)
    reasoning = db.Column(db.String(500))
    tls = db.Column(db.Float)
    qty = db.Column(db.Integer, nullable=True)
    exit_dt = db.Column(db.Date, nullable=True)
    exit_price = db.Column(db.Float, nullable=True)

    trades = db.relationship('Trade', back_populates='trade_recommendation')

class Trade(db.Model):
    __tablename__ = 'trades'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    trade_recommendation_id = db.Column(db.Integer, db.ForeignKey('trade_recommendations.id'))
    script_name = db.Column(db.String(100)) 
    purchase_dt = db.Column(db.Date)
    purchase_price = db.Column(db.Float)
    exit_dt = db.Column(db.Date, nullable=True)
    exit_price = db.Column(db.Float, nullable=True)
    qty = db.Column(db.Integer)
    tls = db.Column(db.Float)
    status = db.Column(db.String(50))  # ongoing, exited, failed, etc.

    user = db.relationship('User', back_populates='trades')
    trade_recommendation = db.relationship('TradeRecommendation', back_populates='trades')

import json
from sqlalchemy import create_engine, inspect

def get_db_schema_to_json():
    # adjust: username, password, host, dbname
    engine = create_engine('mysql+pymysql://root:admin@localhost/bot_2025')

    inspector = inspect(engine)

    schema = {}

    for table_name in inspector.get_table_names():
        table_info = {}

        # Columns
        columns = []
        for col in inspector.get_columns(table_name):
            col_info = {
                'name': col['name'],
                'type': str(col['type']),
                'nullable': col['nullable'],
                'default': str(col.get('default')) if col.get('default') is not None else None
            }
            columns.append(col_info)
        table_info['columns'] = columns

        # Primary key
        pk = inspector.get_pk_constraint(table_name)
        table_info['primary_key'] = pk.get('constrained_columns', [])

        # Foreign keys
        fks = []
        for fk in inspector.get_foreign_keys(table_name):
            fk_info = {
                'constrained_columns': fk['constrained_columns'],
                'referred_table': fk['referred_table'],
                'referred_columns': fk['referred_columns']
            }
            fks.append(fk_info)
        table_info['foreign_keys'] = fks

        # Indexes
        indexes = []
        for idx in inspector.get_indexes(table_name):
            idx_info = {
                'name': idx['name'],
                'column_names': idx['column_names'],
                'unique': idx['unique']
            }
            indexes.append(idx_info)
        table_info['indexes'] = indexes

        # Add table info to schema
        schema[table_name] = table_info

    # Dump to JSON string (pretty)
    json_schema = json.dumps(schema, indent=2)
    print(json_schema)

    return json_schema
    # # Optional: save to file
    # with open('db_schema.json', 'w') as f:
    #     f.write(json_schema)

    # print("\n✅ Schema saved to db_schema.json")