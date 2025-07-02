import sqlite3
import logging

logger = logging.getLogger(__name__)

def get_db_connection():
    """Get database connection with error handling"""
    try:
        conn = sqlite3.connect('iceai.db')
        conn.row_factory = sqlite3.Row
        return conn
    except sqlite3.Error as e:
        logger.error(f"Database connection error: {e}")
        raise

def init_db():
    """Initialize database with all required tables"""
    try:
        conn = sqlite3.connect('iceai.db')
        c = conn.cursor()
        
        # Users table
        c.execute('''CREATE TABLE IF NOT EXISTS users
                     (id TEXT PRIMARY KEY, username TEXT, avatar TEXT, discriminator TEXT,
                      verified INTEGER DEFAULT 0, verification_code TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
        
        # Vouches table
        c.execute('''CREATE TABLE IF NOT EXISTS vouches
                     (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT, target_user_id TEXT,
                      message TEXT, rating INTEGER CHECK(rating >= 1 AND rating <= 5), 
                      trade_type TEXT, account_rank TEXT, price REAL CHECK(price >= 0), 
                      payment_method TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                      FOREIGN KEY(user_id) REFERENCES users(id))''')
        
        # Tickets table
        c.execute('''CREATE TABLE IF NOT EXISTS tickets
                     (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT, ticket_type TEXT,
                      status TEXT DEFAULT 'open' CHECK(status IN ('open', 'closed', 'pending')), 
                      subject TEXT NOT NULL, description TEXT NOT NULL,
                      created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, closed_at TIMESTAMP,
                      FOREIGN KEY(user_id) REFERENCES users(id))''')
        
        # R6 Accounts table
        c.execute('''CREATE TABLE IF NOT EXISTS r6_accounts
                     (id INTEGER PRIMARY KEY AUTOINCREMENT, seller_id TEXT, title TEXT NOT NULL,
                      rank TEXT, level INTEGER CHECK(level >= 0), operators_count INTEGER CHECK(operators_count >= 0), 
                      renown INTEGER CHECK(renown >= 0), r6_credits INTEGER CHECK(r6_credits >= 0), 
                      price REAL CHECK(price >= 0), description TEXT, 
                      status TEXT DEFAULT 'available' CHECK(status IN ('available', 'sold', 'pending')),
                      images TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                      FOREIGN KEY(seller_id) REFERENCES users(id))''')
        
        # Additional tables (keeping essential ones only for space)
        _create_additional_tables(c)
        
        conn.commit()
        logger.info("Database initialized successfully")
        
    except sqlite3.Error as e:
        logger.error(f"Database initialization error: {e}")
        raise
    finally:
        if conn:
            conn.close()

def _create_additional_tables(cursor):
    """Create additional tables"""
    tables = [
        '''CREATE TABLE IF NOT EXISTS invites
           (id INTEGER PRIMARY KEY AUTOINCREMENT, inviter_id TEXT, invited_id TEXT,
            invite_code TEXT UNIQUE, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(inviter_id) REFERENCES users(id))''',
        
        '''CREATE TABLE IF NOT EXISTS giveaways
           (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL, description TEXT,
            prize TEXT NOT NULL, winners_count INTEGER CHECK(winners_count > 0), 
            end_time TIMESTAMP, channel_id TEXT, message_id TEXT, 
            status TEXT DEFAULT 'active' CHECK(status IN ('active', 'ended', 'cancelled')))''',
        
        '''CREATE TABLE IF NOT EXISTS settings
           (key TEXT PRIMARY KEY, value TEXT)''',
        
        '''CREATE TABLE IF NOT EXISTS autoresponder
           (id INTEGER PRIMARY KEY AUTOINCREMENT, trigger_phrase TEXT NOT NULL,
            response TEXT NOT NULL, embed_enabled INTEGER DEFAULT 0,
            embed_data TEXT, enabled INTEGER DEFAULT 1)'''
    ]
    
    for table_sql in tables:
        cursor.execute(table_sql)