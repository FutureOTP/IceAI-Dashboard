import sqlite3
import logging
from flask import jsonify
from database import get_db_connection

logger = logging.getLogger(__name__)

def validate_input(data, required_fields):
    """Validate input data"""
    errors = []
    for field in required_fields:
        if field not in data or not data[field] or str(data[field]).strip() == "":
            errors.append(f"{field} is required")
    return errors

class DashboardService:
    @staticmethod
    def get_user_stats(user_id):
        """Get user statistics for dashboard"""
        try:
            conn = get_db_connection()
            c = conn.cursor()
            
            stats = {}
            
            # Get counts with fallback to 0
            queries = {
                "vouches": "SELECT COUNT(*) FROM vouches WHERE target_user_id = ?",
                "tickets": "SELECT COUNT(*) FROM tickets WHERE user_id = ?",
                "accounts_listed": "SELECT COUNT(*) FROM r6_accounts WHERE seller_id = ?",
            }
            
            for key, query in queries.items():
                c.execute(query, (user_id,))
                stats[key] = c.fetchone()[0] or 0
            
            # Get average rating
            c.execute("SELECT AVG(rating) FROM vouches WHERE target_user_id = ?", (user_id,))
            avg_rating = c.fetchone()[0]
            stats["avg_rating"] = round(float(avg_rating), 1) if avg_rating else 0
            
            # Set defaults
            stats.update({
                "invites": 0,
                "total_trades": 0,
                "total_earnings": 0,
                "member_since": "2024"
            })
            
            return stats
            
        except sqlite3.Error as e:
            logger.error(f"Database error in dashboard: {e}")
            return {"vouches": 0, "tickets": 0, "invites": 0, "accounts_listed": 0,
                   "total_trades": 0, "total_earnings": 0, "avg_rating": 0, "member_since": "2024"}
        finally:
            if conn:
                conn.close()

class TicketService:
    @staticmethod
    def get_user_tickets(user_id):
        """Get tickets for a user"""
        try:
            conn = get_db_connection()
            c = conn.cursor()
            c.execute("SELECT * FROM tickets WHERE user_id = ? ORDER BY created_at DESC", (user_id,))
            return c.fetchall()
        except sqlite3.Error as e:
            logger.error(f"Database error getting tickets: {e}")
            return []
        finally:
            if conn:
                conn.close()
    
    @staticmethod
    def create_ticket(user_id, data):
        """Create a new ticket"""
        try:
            if not data:
                return jsonify({"error": "No data provided"}), 400
                
            errors = validate_input(data, ["type", "subject", "description"])
            if errors:
                return jsonify({"error": "Validation failed", "details": errors}), 400
                
            conn = get_db_connection()
            c = conn.cursor()
            c.execute("INSERT INTO tickets (user_id, ticket_type, subject, description) VALUES (?, ?, ?, ?)",
                      (user_id, data["type"], data["subject"], data["description"]))
            ticket_id = c.lastrowid
            conn.commit()
            
            return jsonify({"success": True, "ticket_id": ticket_id})
            
        except sqlite3.Error as e:
            logger.error(f"Database error creating ticket: {e}")
            return jsonify({"error": "Database error"}), 500
        finally:
            if conn:
                conn.close()

class VouchService:
    @staticmethod
    def get_user_vouches(user_id):
        """Get vouches for a user"""
        try:
            conn = get_db_connection()
            c = conn.cursor()
            c.execute("SELECT * FROM vouches WHERE user_id = ? ORDER BY created_at DESC", (user_id,))
            return c.fetchall()
        except sqlite3.Error as e:
            logger.error(f"Database error getting vouches: {e}")
            return []
        finally:
            if conn:
                conn.close()
    
    @staticmethod
    def create_vouch(user_id, data):
        """Create a new vouch"""
        try:
            if not data:
                return jsonify({"error": "No data provided"}), 400
                
            errors = validate_input(data, ["target", "message", "rating"])
            if errors:
                return jsonify({"error": "Validation failed", "details": errors}), 400
                
            # Validate rating
            try:
                rating = int(data["rating"])
                if rating < 1 or rating > 5:
                    return jsonify({"error": "Rating must be between 1 and 5"}), 400
            except (ValueError, TypeError):
                return jsonify({"error": "Invalid rating format"}), 400
                
            conn = get_db_connection()
            c = conn.cursor()
            c.execute("""INSERT INTO vouches (user_id, target_user_id, message, rating, trade_type, account_rank, price, payment_method) 
                         VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                      (user_id, data["target"], data["message"], rating, 
                       data.get("trade_type", ""), data.get("account_rank", ""), 
                       data.get("price", 0), data.get("payment_method", "")))
            conn.commit()
            
            return jsonify({"success": True})
            
        except sqlite3.Error as e:
            logger.error(f"Database error creating vouch: {e}")
            return jsonify({"error": "Database error"}), 500
        finally:
            if conn:
                conn.close()

class MarketplaceService:
    @staticmethod
    def get_accounts():
        """Get available R6 accounts"""
        try:
            conn = get_db_connection()
            c = conn.cursor()
            c.execute("SELECT * FROM r6_accounts WHERE status = 'available' ORDER BY created_at DESC LIMIT 100")
            accounts = c.fetchall()
            
            return jsonify([{
                "id": a[0], "title": a[2], "rank": a[3], "level": a[4],
                "operators": a[5], "renown": a[6], "credits": a[7], 
                "price": a[8], "description": a[9], "created_at": a[11]
            } for a in accounts])
            
        except sqlite3.Error as e:
            logger.error(f"Database error getting accounts: {e}")
            return jsonify({"error": "Database error"}), 500
        finally:
            if conn:
                conn.close()
    
    @staticmethod
    def create_account_listing(user_id, data):
        """Create a new account listing"""
        try:
            if not data:
                return jsonify({"error": "No data provided"}), 400
                
            errors = validate_input(data, ["title", "rank", "level", "price"])
            if errors:
                return jsonify({"error": "Validation failed", "details": errors}), 400
                
            # Validate numeric fields
            try:
                level = int(data["level"])
                price = float(data["price"])
                operators = int(data.get("operators", 0))
                renown = int(data.get("renown", 0))
                credits = int(data.get("credits", 0))
                
                if any(val < 0 for val in [level, price, operators, renown, credits]):
                    return jsonify({"error": "Numeric values must be non-negative"}), 400
                    
            except (ValueError, TypeError):
                return jsonify({"error": "Invalid numeric values"}), 400
                
            conn = get_db_connection()
            c = conn.cursor()
            c.execute("""INSERT INTO r6_accounts 
                         (seller_id, title, rank, level, operators_count, renown, r6_credits, price, description) 
                         VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                      (user_id, data["title"], data["rank"], level, 
                       operators, renown, credits, price, data.get("description", "")))
            conn.commit()
            return jsonify({"success": True})
            
        except sqlite3.Error as e:
            logger.error(f"Database error creating listing: {e}")
            return jsonify({"error": "Database error"}), 500
        finally:
            if conn:
                conn.close()