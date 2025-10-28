import yfinance as yf
import pandas as pd
import matplotlib.pyplot as plt
import customtkinter as ctk
import tkinter as tk
from tkinter import ttk, messagebox
import csv
from datetime import datetime, timedelta
import os
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import threading
import json

# ----------------- Helper Functions -----------------
def get_full_ticker(ticker, market):
    ticker = ticker.upper()
    suffix_map = {
        "NSE": ".NS",
        "BSE": ".BO",
        "NASDAQ": "",
        "NYSE": "",
        "LSE": ".L",
        "EURONEXT": ".PA",
        "HKEX": ".HK",
        "SSE": ".SS",
        "SZSE": ".SZ"
    }
    suffix = suffix_map.get(market, "")
    if suffix and not ticker.endswith(suffix):
        ticker += suffix
    return ticker

# ----------------- File Paths -----------------
PORTFOLIO_CSV = "portfolio.csv"
LOG_CSV = "update_log.csv"
ALERTS_JSON = "price_alerts.json"
PERFORMANCE_CSV = "performance_history.csv"
TARIFF_EVENTS_JSON = "tariff_events.json"
GREEN_BONDS_JSON = "green_bonds.json"

if not os.path.exists(LOG_CSV):
    with open(LOG_CSV, mode="w", newline="") as logfile:
        writer = csv.writer(logfile)
        writer.writerow(["Sl.No", "Date", "Time", "Share Name", "Ticker", "Market", "Price at log", "Additional Info"])

if not os.path.exists(ALERTS_JSON):
    with open(ALERTS_JSON, "w") as f:
        json.dump({}, f)

if not os.path.exists(TARIFF_EVENTS_JSON):
    with open(TARIFF_EVENTS_JSON, "w") as f:
        json.dump({"events": []}, f)

if not os.path.exists(GREEN_BONDS_JSON):
    with open(GREEN_BONDS_JSON, "w") as f:
        json.dump({"bonds": []}, f)

if not os.path.exists(PERFORMANCE_CSV):
    with open(PERFORMANCE_CSV, mode="w", newline="") as perffile:
        writer = csv.writer(perffile)
        writer.writerow(["Date", "Total Value INR", "Total P/L INR"])

# ----------------- Logging -----------------
def get_next_serial():
    if os.path.exists(LOG_CSV):
        with open(LOG_CSV, "r") as logfile:
            reader = csv.reader(logfile)
            rows = list(reader)
            return len(rows)
    else:
        return 1

def log_update(share_name, ticker, market, price_at_log, additional_info):
    sl_no = get_next_serial()
    now = datetime.now()
    date_str = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%H:%M:%S")
    log_entry = [sl_no, date_str, time_str, share_name, ticker, market, price_at_log, additional_info]
    with open(LOG_CSV, mode="a", newline="") as logfile:
        writer = csv.writer(logfile)
        writer.writerow(log_entry)

def save_portfolio_csv(portfolio):
    with open(PORTFOLIO_CSV, mode="w", newline="") as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(["Ticker", "Shares", "Buy Price", "Market"])
        for full_ticker, data in portfolio.items():
            writer.writerow([full_ticker, data['shares'], data['buy_price'], data['market']])

def log_performance(total_value, total_pl):
    date_str = datetime.now().strftime("%Y-%m-%d")
    with open(PERFORMANCE_CSV, mode="a", newline="") as perffile:
        writer = csv.writer(perffile)
        writer.writerow([date_str, total_value, total_pl])

CURRENCY_MAP = {
    "NSE": "INR",
    "BSE": "INR",
    "NASDAQ": "USD",
    "NYSE": "USD",
    "LSE": "GBP",
    "EURONEXT": "EUR",
    "HKEX": "HKD",
    "SSE": "CNY",
    "SZSE": "CNY"
}

FX_CACHE = {}

def get_fx_rate_to_inr(currency):
    if currency == "INR":
        return 1.0
    if currency in FX_CACHE and (datetime.now() - FX_CACHE[currency]['time']).total_seconds() < 3600:
        return FX_CACHE[currency]['rate']
    try:
        pair = f"{currency}INR=X"
        fx = yf.Ticker(pair)
        hist = fx.history(period="1d")
        rate = hist["Close"].iloc[-1]
        FX_CACHE[currency] = {"rate": rate, "time": datetime.now()}
        return rate
    except Exception:
        return 1.0

# ----------------- Alert Manager -----------------
class AlertManager:
    def __init__(self):
        self.alerts = self.load_alerts()
    
    def load_alerts(self):
        try:
            with open(ALERTS_JSON, "r") as f:
                return json.load(f)
        except:
            return {}
    
    def save_alerts(self):
        with open(ALERTS_JSON, "w") as f:
            json.dump(self.alerts, f, indent=2)
    
    def add_alert(self, ticker, target_price, alert_type):
        if ticker not in self.alerts:
            self.alerts[ticker] = []
        self.alerts[ticker].append({
            "target_price": target_price,
            "type": alert_type,
            "created": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        })
        self.save_alerts()
    
    def remove_alert(self, ticker, index):
        if ticker in self.alerts and index < len(self.alerts[ticker]):
            self.alerts[ticker].pop(index)
            if not self.alerts[ticker]:
                del self.alerts[ticker]
            self.save_alerts()
    
    def check_alerts(self, ticker, current_price):
        triggered = []
        if ticker not in self.alerts:
            return triggered
        
        remaining = []
        for alert in self.alerts[ticker]:
            target = alert['target_price']
            alert_type = alert['type']
            
            if (alert_type == "above" and current_price >= target) or \
               (alert_type == "below" and current_price <= target):
                triggered.append(alert)
            else:
                remaining.append(alert)
        
        self.alerts[ticker] = remaining
        if not remaining:
            del self.alerts[ticker]
        self.save_alerts()
        
        return triggered

# ----------------- Tariff Impact Analyzer -----------------
class TariffAnalyzer:
    def __init__(self):
        self.events = self.load_events()
        self.country_trade_routes = {
            "NSE": {"country": "India", "major_partners": ["USA", "China", "UAE", "Saudi Arabia"]},
            "BSE": {"country": "India", "major_partners": ["USA", "China", "UAE", "Saudi Arabia"]},
            "NASDAQ": {"country": "USA", "major_partners": ["China", "Mexico", "Canada", "EU"]},
            "NYSE": {"country": "USA", "major_partners": ["China", "Mexico", "Canada", "EU"]},
            "LSE": {"country": "UK", "major_partners": ["EU", "USA", "China"]},
            "EURONEXT": {"country": "EU", "major_partners": ["USA", "China", "UK"]},
            "HKEX": {"country": "China", "major_partners": ["USA", "EU", "ASEAN"]},
            "SSE": {"country": "China", "major_partners": ["USA", "EU", "ASEAN"]},
            "SZSE": {"country": "China", "major_partners": ["USA", "EU", "ASEAN"]}
        }
    
    def load_events(self):
        try:
            with open(TARIFF_EVENTS_JSON, "r") as f:
                data = json.load(f)
                return data.get("events", [])
        except:
            return []
    
    def save_events(self):
        with open(TARIFF_EVENTS_JSON, "w") as f:
            json.dump({"events": self.events}, f, indent=2)
    
    def add_tariff_event(self, source_country, target_country, affected_sectors, tariff_rate, description, date):
        event = {
            "id": len(self.events) + 1,
            "source_country": source_country,
            "target_country": target_country,
            "affected_sectors": affected_sectors,
            "tariff_rate": tariff_rate,
            "description": description,
            "date": date,
            "created": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        self.events.append(event)
        self.save_events()
        return event
    
    def remove_event(self, event_id):
        self.events = [e for e in self.events if e.get("id") != event_id]
        self.save_events()
    
    def analyze_stock_exposure(self, ticker, market, sector, industry):
        if not sector or sector == "Unknown":
            return {"risk_level": "Unknown", "affected_events": [], "impact_score": 0}
        
        stock_country = self.country_trade_routes.get(market, {}).get("country", "Unknown")
        trade_partners = self.country_trade_routes.get(market, {}).get("major_partners", [])
        
        affected_events = []
        impact_score = 0
        
        for event in self.events:
            event_affects_stock = False
            impact_reason = []
            
            if event["target_country"] == stock_country:
                for affected_sector in event["affected_sectors"]:
                    if affected_sector.lower() in sector.lower() or \
                       affected_sector.lower() in industry.lower():
                        event_affects_stock = True
                        impact_reason.append(f"Direct tariff on {sector} from {event['source_country']}")
                        impact_score += event["tariff_rate"] * 0.5
            
            elif event["source_country"] == stock_country:
                for affected_sector in event["affected_sectors"]:
                    if affected_sector.lower() in sector.lower():
                        event_affects_stock = True
                        impact_reason.append(f"Export restrictions to {event['target_country']}")
                        impact_score += event["tariff_rate"] * 0.3
            
            elif event["target_country"] in trade_partners or event["source_country"] in trade_partners:
                for affected_sector in event["affected_sectors"]:
                    if affected_sector.lower() in sector.lower():
                        event_affects_stock = True
                        impact_reason.append(f"Supply chain disruption: {event['source_country']} - {event['target_country']}")
                        impact_score += event["tariff_rate"] * 0.2
            
            if event_affects_stock:
                affected_events.append({
                    "event": event,
                    "reasons": impact_reason
                })
        
        if impact_score >= 30:
            risk_level = "HIGH RISK"
        elif impact_score >= 15:
            risk_level = "MODERATE RISK"
        elif impact_score > 0:
            risk_level = "LOW RISK"
        else:
            risk_level = "NO TARIFF IMPACT"
        
        return {
            "risk_level": risk_level,
            "affected_events": affected_events,
            "impact_score": round(impact_score, 2),
            "stock_country": stock_country,
            "sector": sector
        }
    
    def get_portfolio_tariff_summary(self, portfolio_data):
        high_risk = []
        moderate_risk = []
        low_risk = []
        total_exposure = 0
        
        for stock_data in portfolio_data:
            exposure = stock_data.get("tariff_analysis", {})
            impact = exposure.get("impact_score", 0)
            
            if impact >= 30:
                high_risk.append(stock_data)
            elif impact >= 15:
                moderate_risk.append(stock_data)
            elif impact > 0:
                low_risk.append(stock_data)
            
            total_exposure += impact
        
        return {
            "high_risk_count": len(high_risk),
            "moderate_risk_count": len(moderate_risk),
            "low_risk_count": len(low_risk),
            "high_risk_stocks": high_risk,
            "moderate_risk_stocks": moderate_risk,
            "total_exposure_score": round(total_exposure, 2)
        }

# ----------------- Green Bonds Tracker -----------------
class GreenBondsTracker:
    def __init__(self):
        self.bonds = self.load_bonds()
        self.esg_sectors = {
            "Renewable Energy": {"impact": "High", "color": "#2ecc71"},
            "Green Buildings": {"impact": "Medium", "color": "#3498db"},
            "Clean Transportation": {"impact": "High", "color": "#1abc9c"},
            "Water Management": {"impact": "Medium", "color": "#16a085"},
            "Pollution Prevention": {"impact": "Medium", "color": "#27ae60"},
            "Sustainable Agriculture": {"impact": "Medium", "color": "#f39c12"},
            "Biodiversity": {"impact": "High", "color": "#8e44ad"},
            "Climate Adaptation": {"impact": "High", "color": "#c0392b"}
        }
        
        self.rating_scores = {
            "AAA": 10, "AA+": 9, "AA": 8, "AA-": 7,
            "A+": 6, "A": 5, "A-": 4,
            "BBB+": 3, "BBB": 2, "BBB-": 1,
            "BB+": 0, "BB": -1, "BB-": -2,
            "B+": -3, "B": -4, "B-": -5
        }
    
    def load_bonds(self):
        try:
            with open(GREEN_BONDS_JSON, "r") as f:
                data = json.load(f)
                return data.get("bonds", [])
        except:
            return []
    
    def save_bonds(self):
        with open(GREEN_BONDS_JSON, "w") as f:
            json.dump({"bonds": self.bonds}, f, indent=2)
    
    def add_bond(self, issuer, bond_name, isin, coupon_rate, maturity_date, issue_size, 
                 currency, credit_rating, green_category, esg_impact, current_yield, purchase_amount):
        bond = {
            "id": len(self.bonds) + 1,
            "issuer": issuer,
            "bond_name": bond_name,
            "isin": isin,
            "coupon_rate": coupon_rate,
            "maturity_date": maturity_date,
            "issue_size": issue_size,
            "currency": currency,
            "credit_rating": credit_rating,
            "green_category": green_category,
            "esg_impact": esg_impact,
            "current_yield": current_yield,
            "purchase_amount": purchase_amount,
            "purchase_date": datetime.now().strftime("%Y-%m-%d"),
            "price_history": []
        }
        self.bonds.append(bond)
        self.save_bonds()
        return bond
    
    def remove_bond(self, bond_id):
        self.bonds = [b for b in self.bonds if b.get("id") != bond_id]
        self.save_bonds()
    
    def update_bond_yield(self, bond_id, new_yield):
        for bond in self.bonds:
            if bond.get("id") == bond_id:
                bond["current_yield"] = new_yield
                bond["price_history"].append({
                    "date": datetime.now().strftime("%Y-%m-%d"),
                    "yield": new_yield
                })
                self.save_bonds()
                return True
        return False
    
    def calculate_bond_score(self, bond):
        score = 50
        
        rating = bond.get("credit_rating", "BBB")
        rating_score = self.rating_scores.get(rating, 0)
        score += rating_score * 2
        
        esg_impact = bond.get("esg_impact", "Medium")
        if esg_impact == "High":
            score += 15
        elif esg_impact == "Medium":
            score += 8
        elif esg_impact == "Low":
            score += 3
        
        current_yield = bond.get("current_yield", 0)
        if current_yield > 7:
            score += 15
        elif current_yield > 5:
            score += 10
        elif current_yield > 3:
            score += 5
        
        try:
            maturity = datetime.strptime(bond.get("maturity_date"), "%Y-%m-%d")
            years_to_maturity = (maturity - datetime.now()).days / 365
            if 3 <= years_to_maturity <= 7:
                score += 10
            elif 1 <= years_to_maturity <= 10:
                score += 5
        except:
            pass
        
        return min(max(score, 0), 100)
    
    def get_bond_recommendation(self, bond):
        score = self.calculate_bond_score(bond)
        
        recommendations = []
        
        if score >= 80:
            overall = "🟢 STRONG BUY - Excellent green bond investment"
        elif score >= 65:
            overall = "🟢 BUY - Good sustainable investment opportunity"
        elif score >= 50:
            overall = "🟡 HOLD - Moderate green bond, consider alternatives"
        elif score >= 35:
            overall = "🟠 CAUTION - Below average, high risk"
        else:
            overall = "🔴 AVOID - Poor investment metrics"
        
        rating = bond.get("credit_rating", "N/A")
        if rating in ["AAA", "AA+", "AA"]:
            recommendations.append("✓ Excellent credit quality - Very low default risk")
        elif rating in ["AA-", "A+", "A"]:
            recommendations.append("✓ Good credit quality - Low risk")
        elif rating in ["A-", "BBB+", "BBB"]:
            recommendations.append("◉ Investment grade - Moderate risk")
        else:
            recommendations.append("✗ Below investment grade - Higher risk")
        
        current_yield = bond.get("current_yield", 0)
        if current_yield > 6:
            recommendations.append(f"✓ Attractive yield: {current_yield}% - Above market average")
        elif current_yield > 4:
            recommendations.append(f"◉ Moderate yield: {current_yield}% - Market average")
        else:
            recommendations.append(f"✗ Low yield: {current_yield}% - Below expectations")
        
        esg_impact = bond.get("esg_impact", "Medium")
        category = bond.get("green_category", "Unknown")
        if esg_impact == "High":
            recommendations.append(f"✓ High ESG impact in {category} - Strong sustainability credentials")
        elif esg_impact == "Medium":
            recommendations.append(f"◉ Medium ESG impact in {category} - Good green credentials")
        else:
            recommendations.append(f"✗ Low ESG impact - Limited sustainability benefit")
        
        try:
            maturity = datetime.strptime(bond.get("maturity_date"), "%Y-%m-%d")
            years = (maturity - datetime.now()).days / 365
            if 3 <= years <= 7:
                recommendations.append(f"✓ Optimal maturity: {years:.1f} years - Balanced risk/return")
            elif years < 2:
                recommendations.append(f"◉ Short maturity: {years:.1f} years - Lower interest rate risk")
            else:
                recommendations.append(f"◉ Long maturity: {years:.1f} years - Higher interest rate risk")
        except:
            recommendations.append("⚠ Maturity information unavailable")
        
        return {
            "score": score,
            "recommendation": overall,
            "details": recommendations
        }
    
    def get_portfolio_analysis(self):
        if not self.bonds:
            return None
        
        total_investment = sum(b.get("purchase_amount", 0) for b in self.bonds)
        avg_yield = sum(b.get("current_yield", 0) for b in self.bonds) / len(self.bonds)
        
        category_allocation = {}
        for bond in self.bonds:
            cat = bond.get("green_category", "Unknown")
            amt = bond.get("purchase_amount", 0)
            category_allocation[cat] = category_allocation.get(cat, 0) + amt
        
        impact_counts = {"High": 0, "Medium": 0, "Low": 0}
        for bond in self.bonds:
            impact = bond.get("esg_impact", "Medium")
            impact_counts[impact] = impact_counts.get(impact, 0) + 1
        
        avg_score = sum(self.calculate_bond_score(b) for b in self.bonds) / len(self.bonds)
        
        return {
            "total_bonds": len(self.bonds),
            "total_investment": total_investment,
            "avg_yield": avg_yield,
            "avg_score": avg_score,
            "category_allocation": category_allocation,
            "impact_distribution": impact_counts
        }

# ----------------- StockManager -----------------
class StockManager:
    def __init__(self):
        self.portfolio = {}
        self.alert_manager = AlertManager()
        self.tariff_analyzer = TariffAnalyzer()
        self.green_bonds_tracker = GreenBondsTracker()
        if os.path.exists(PORTFOLIO_CSV):
            self.load_portfolio_csv()

    def load_portfolio_csv(self):
        try:
            df = pd.read_csv(PORTFOLIO_CSV)
            for _, row in df.iterrows():
                self.portfolio[row['Ticker']] = {
                    'shares': float(row['Shares']),
                    'buy_price': float(row['Buy Price']),
                    'market': row['Market']
                }
        except Exception as e:
            print(f"Error loading portfolio CSV: {e}")

    def add_stock(self, ticker, shares, buy_price, market):
        full_ticker = get_full_ticker(ticker, market)
        self.portfolio[full_ticker] = {'shares': shares, 'buy_price': buy_price, 'market': market}
        save_portfolio_csv(self.portfolio)
        log_update(ticker.upper(), full_ticker, market, buy_price, f"Added with {shares} shares")
    
    def delete_stock(self, full_ticker):
        if full_ticker in self.portfolio:
            del self.portfolio[full_ticker]
            save_portfolio_csv(self.portfolio)
            log_update(full_ticker, full_ticker, "", "", "Deleted stock")
    
    def fetch_live_price(self, full_ticker):
        try:
            stock = yf.Ticker(full_ticker)
            hist = stock.history(period='5d')
            if hist.empty:
                return None
            price = hist['Close'].iloc[-1]
            return price
        except Exception as e:
            print(f"Error fetching live price for {full_ticker}: {e}")
            return None
    
    def get_stock_info(self, full_ticker):
        try:
            stock = yf.Ticker(full_ticker)
            info = stock.info
            return info
        except Exception as e:
            print(f"Error fetching stock info: {e}")
            return {}
    
    def advanced_recommendation(self, ticker, market):
        full_ticker = get_full_ticker(ticker, market)
        try:
            stock = yf.Ticker(full_ticker)
            hist = stock.history(period='1y')
            
            if hist.empty or len(hist) < 50:
                return {"recommendation": "Insufficient data for analysis", "signals": []}
            
            hist['SMA_50'] = hist['Close'].rolling(window=50).mean()
            hist['SMA_200'] = hist['Close'].rolling(window=200).mean()
            hist['EMA_12'] = hist['Close'].ewm(span=12, adjust=False).mean()
            hist['EMA_26'] = hist['Close'].ewm(span=26, adjust=False).mean()
            
            delta = hist['Close'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
            rs = gain / loss
            hist['RSI'] = 100 - (100 / (1 + rs))
            
            hist['MACD'] = hist['EMA_12'] - hist['EMA_26']
            hist['Signal_Line'] = hist['MACD'].ewm(span=9, adjust=False).mean()
            
            hist['BB_Middle'] = hist['Close'].rolling(window=20).mean()
            bb_std = hist['Close'].rolling(window=20).std()
            hist['BB_Upper'] = hist['BB_Middle'] + (bb_std * 2)
            hist['BB_Lower'] = hist['BB_Middle'] - (bb_std * 2)
            
            latest = hist.iloc[-1]
            latest_price = latest['Close']
            
            signals = []
            buy_score = 0
            sell_score = 0
            
            if pd.notna(latest['SMA_50']) and pd.notna(latest['SMA_200']):
                if latest['SMA_50'] > latest['SMA_200']:
                    signals.append("✓ Golden Cross: 50-day MA above 200-day MA (Bullish)")
                    buy_score += 2
                else:
                    signals.append("✗ Death Cross: 50-day MA below 200-day MA (Bearish)")
                    sell_score += 2
            
            if pd.notna(latest['SMA_50']):
                if latest_price > latest['SMA_50']:
                    signals.append("✓ Price above 50-day MA (Bullish)")
                    buy_score += 1
                else:
                    signals.append("✗ Price below 50-day MA (Bearish)")
                    sell_score += 1
            
            if pd.notna(latest['RSI']):
                rsi_val = latest['RSI']
                if rsi_val < 30:
                    signals.append(f"✓ RSI ({rsi_val:.1f}): Oversold - Potential Buy")
                    buy_score += 2
                elif rsi_val > 70:
                    signals.append(f"✗ RSI ({rsi_val:.1f}): Overbought - Potential Sell")
                    sell_score += 2
                else:
                    signals.append(f"◉ RSI ({rsi_val:.1f}): Neutral")
            
            if pd.notna(latest['MACD']) and pd.notna(latest['Signal_Line']):
                if latest['MACD'] > latest['Signal_Line']:
                    signals.append("✓ MACD above Signal Line (Bullish)")
                    buy_score += 1
                else:
                    signals.append("✗ MACD below Signal Line (Bearish)")
                    sell_score += 1
            
            if pd.notna(latest['BB_Upper']) and pd.notna(latest['BB_Lower']):
                if latest_price < latest['BB_Lower']:
                    signals.append("✓ Price near Lower Bollinger Band (Oversold)")
                    buy_score += 1
                elif latest_price > latest['BB_Upper']:
                    signals.append("✗ Price near Upper Bollinger Band (Overbought)")
                    sell_score += 1
            
            avg_volume = hist['Volume'].tail(20).mean()
            recent_volume = latest['Volume']
            if recent_volume > avg_volume * 1.5:
                signals.append(f"⚡ High Volume: {recent_volume/1000000:.1f}M vs avg {avg_volume/1000000:.1f}M")
            
            if buy_score > sell_score + 2:
                recommendation = "🟢 STRONG BUY"
            elif buy_score > sell_score:
                recommendation = "🟢 BUY"
            elif sell_score > buy_score + 2:
                recommendation = "🔴 STRONG SELL"
            elif sell_score > buy_score:
                recommendation = "🔴 SELL"
            else:
                recommendation = "🟡 HOLD"
            
            return {
                "recommendation": recommendation,
                "signals": signals,
                "score": f"Buy Score: {buy_score} | Sell Score: {sell_score}",
                "price": latest_price
            }
            
        except Exception as e:
            return {"recommendation": f"Error: {str(e)}", "signals": []}
    
    def get_stock_chart_data(self, ticker, market, period='6mo'):
        full_ticker = get_full_ticker(ticker, market)
        try:
            stock = yf.Ticker(full_ticker)
            hist = stock.history(period=period)
            return hist, full_ticker
        except Exception as e:
            print(f"Error fetching chart data: {e}")
            return None, full_ticker

# ----------------- CustomTkinter GUI -----------------
ctk.set_appearance_mode("Light")
ctk.set_default_color_theme("blue")

class StockManagerGUI(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Professional Stock Management Dashboard")
        self.geometry("1200x700")
        self.stock_manager = StockManager()
        self.last_refresh = None
        
        self.sidebar_width = 200
        self.sidebar_expanded = True
        
        self.sidebar_frame = ctk.CTkFrame(self, width=self.sidebar_width)
        self.sidebar_frame.pack(side="left", fill="y")
        self.sidebar_frame.pack_propagate(False)
        
        self.sidebar_button_frame = ctk.CTkFrame(self.sidebar_frame)
        self.sidebar_button_frame.pack(fill="both", expand=True)
        
        self.btn_dashboard = ctk.CTkButton(self.sidebar_button_frame, text="Dashboard", command=self.show_dashboard, width=180)
        self.btn_dashboard.pack(pady=(20,10), padx=10)
        self.btn_trade = ctk.CTkButton(self.sidebar_button_frame, text="Trade Tools", command=self.show_trade_tools, width=180)
        self.btn_trade.pack(pady=10, padx=10)
        self.btn_analytics = ctk.CTkButton(self.sidebar_button_frame, text="Analytics", command=self.show_analytics, width=180)
        self.btn_analytics.pack(pady=10, padx=10)
        self.btn_alerts = ctk.CTkButton(self.sidebar_button_frame, text="Alerts", command=self.show_alerts, width=180)
        self.btn_alerts.pack(pady=10, padx=10)
        self.btn_performance = ctk.CTkButton(self.sidebar_button_frame, text="Performance", command=self.show_performance, width=180)
        self.btn_performance.pack(pady=10, padx=10)
        self.btn_tariffs = ctk.CTkButton(self.sidebar_button_frame, text="Tariff Impact", command=self.show_tariffs, width=180, fg_color="orange")
        self.btn_tariffs.pack(pady=10, padx=10)
        self.btn_green_bonds = ctk.CTkButton(self.sidebar_button_frame, text="Green Bonds", command=self.show_green_bonds, width=180, fg_color="#2ecc71")
        self.btn_green_bonds.pack(pady=10, padx=10)
        
        self.btn_toggle = ctk.CTkButton(self.sidebar_frame, text="Collapse", command=self.toggle_sidebar, width=180)
        self.btn_toggle.pack(side="bottom", pady=10, padx=10)
        
        self.main_frame = ctk.CTkFrame(self)
        self.main_frame.pack(side="left", fill="both", expand=True)
        
        self.dashboard_content = ctk.CTkFrame(self.main_frame)
        self.trade_content = ctk.CTkFrame(self.main_frame)
        self.analytics_content = ctk.CTkFrame(self.main_frame)
        self.alerts_content = ctk.CTkFrame(self.main_frame)
        self.performance_content = ctk.CTkFrame(self.main_frame)
        self.tariffs_content = ctk.CTkFrame(self.main_frame)
        self.green_bonds_content = ctk.CTkFrame(self.main_frame)
        
        self.create_dashboard_content(self.dashboard_content)
        self.create_trade_tools_content(self.trade_content)
        self.create_analytics_content(self.analytics_content)
        self.create_alerts_content(self.alerts_content)
        self.create_performance_content(self.performance_content)
        self.create_tariffs_content(self.tariffs_content)
        self.create_green_bonds_content(self.green_bonds_content)
        
        self.show_dashboard()
        self.check_alerts_background()
    
    def toggle_sidebar(self):
        if self.sidebar_expanded:
            self.sidebar_frame.configure(width=50)
            self.sidebar_button_frame.pack_forget()
            self.btn_toggle.configure(text=">")
            self.sidebar_expanded = False
        else:
            self.sidebar_frame.configure(width=self.sidebar_width)
            self.sidebar_button_frame.pack(fill="both", expand=True)
            self.btn_toggle.configure(text="Collapse")
            self.sidebar_expanded = True
        self.sidebar_frame.update_idletasks()
    
    def clear_main_frame(self):
        for widget in self.main_frame.winfo_children():
            widget.pack_forget()
    
    def show_dashboard(self):
        self.clear_main_frame()
        self.dashboard_content.pack(fill="both", expand=True)
    
    def show_trade_tools(self):
        self.clear_main_frame()
        self.trade_content.pack(fill="both", expand=True)
    
    def show_analytics(self):
        self.clear_main_frame()
        self.analytics_content.pack(fill="both", expand=True)
        self.update_analytics()
    
    def show_alerts(self):
        self.clear_main_frame()
        self.alerts_content.pack(fill="both", expand=True)
        self.refresh_alerts_display()
    
    def show_performance(self):
        self.clear_main_frame()
        self.performance_content.pack(fill="both", expand=True)
        self.update_performance_chart()
    
    def show_tariffs(self):
        self.clear_main_frame()
        self.tariffs_content.pack(fill="both", expand=True)
        self.refresh_tariff_display()
    
    def show_green_bonds(self):
        self.clear_main_frame()
        self.green_bonds_content.pack(fill="both", expand=True)
        self.refresh_green_bonds_display()
    
    # ----------------- Dashboard Content -----------------
    def create_dashboard_content(self, frame):
        add_frame = ctk.CTkFrame(frame)
        add_frame.pack(padx=10, pady=10, fill="x")
        
        ctk.CTkLabel(add_frame, text="Ticker:").grid(row=0, column=0, padx=5, pady=5, sticky="w")
        self.ticker_entry = ctk.CTkEntry(add_frame, width=100)
        self.ticker_entry.grid(row=0, column=1, padx=5, pady=5)
        
        ctk.CTkLabel(add_frame, text="Shares:").grid(row=0, column=2, padx=5, pady=5, sticky="w")
        self.shares_entry = ctk.CTkEntry(add_frame, width=80)
        self.shares_entry.grid(row=0, column=3, padx=5, pady=5)
        
        ctk.CTkLabel(add_frame, text="Buy Price:").grid(row=0, column=4, padx=5, pady=5, sticky="w")
        self.buy_price_entry = ctk.CTkEntry(add_frame, width=80)
        self.buy_price_entry.grid(row=0, column=5, padx=5, pady=5)
        
        ctk.CTkLabel(add_frame, text="Market:").grid(row=0, column=6, padx=5, pady=5, sticky="w")
        self.market_var = ctk.StringVar(value="NSE")
        self.market_option = ctk.CTkOptionMenu(
            add_frame,
            variable=self.market_var,
            values=["NSE", "BSE", "NASDAQ", "NYSE", "LSE", "EURONEXT", "HKEX", "SSE", "SZSE"]
        )
        self.market_option.grid(row=0, column=7, padx=5, pady=5)
        
        add_button = ctk.CTkButton(add_frame, text="Add Stock", command=self.add_stock)
        add_button.grid(row=0, column=8, padx=10, pady=5)
        
        delete_button = ctk.CTkButton(add_frame, text="Delete Selected", command=self.delete_stock)
        delete_button.grid(row=0, column=9, padx=10, pady=5)
        
        refresh_frame = ctk.CTkFrame(frame)
        refresh_frame.pack(padx=10, pady=5, fill="x")
        
        self.refresh_button = ctk.CTkButton(refresh_frame, text="🔄 Refresh Prices", command=self.refresh_all_prices, fg_color="green")
        self.refresh_button.pack(side="left", padx=5)
        
        self.last_refresh_label = ctk.CTkLabel(refresh_frame, text="Last refresh: Never")
        self.last_refresh_label.pack(side="left", padx=10)
        
        port_frame = ctk.CTkFrame(frame)
        port_frame.pack(padx=10, pady=10, fill="both", expand=True)
        
        style = ttk.Style()
        style.configure("Custom.Treeview", background="white", fieldbackground="white", foreground="black")
        
        columns = ("Sl. No", "Ticker", "Market", "Shares", "Buy Price", "Current Price", "Profit/Loss", "P/L %")
        self.portfolio_tree = ttk.Treeview(port_frame, columns=columns, show="headings", height=15, style="Custom.Treeview")
        for col in columns:
            self.portfolio_tree.heading(col, text=col)
            self.portfolio_tree.column(col, anchor="center", width=100)
        
        self.portfolio_tree.tag_configure('profit', background='#90EE90')
        self.portfolio_tree.tag_configure('loss', background='#FFB6C1')
        self.portfolio_tree.tag_configure('neutral', background='#FFFACD')
        
        self.portfolio_tree.pack(fill="both", expand=True, padx=10, pady=10)
        self.update_portfolio_display()
    
    def refresh_all_prices(self):
        self.refresh_button.configure(state="disabled", text="Refreshing...")
        
        def refresh_thread():
            self.update_portfolio_display()
            self.last_refresh = datetime.now()
            self.last_refresh_label.configure(text=f"Last refresh: {self.last_refresh.strftime('%H:%M:%S')}")
            self.refresh_button.configure(state="normal", text="🔄 Refresh Prices")
        
        threading.Thread(target=refresh_thread, daemon=True).start()
    
    # ----------------- Trade Tools Content -----------------
    def create_trade_tools_content(self, frame):
        input_frame = ctk.CTkFrame(frame)
        input_frame.pack(padx=10, pady=10, fill="x")
        
        ctk.CTkLabel(input_frame, text="Ticker:").grid(row=0, column=0, padx=5, pady=5, sticky="w")
        self.chart_ticker_entry = ctk.CTkEntry(input_frame, width=100)
        self.chart_ticker_entry.grid(row=0, column=1, padx=5, pady=5)
        
        ctk.CTkLabel(input_frame, text="Market:").grid(row=0, column=2, padx=5, pady=5, sticky="w")
        self.chart_market_var = ctk.StringVar(value="NSE")
        self.chart_market_option = ctk.CTkOptionMenu(
            input_frame,
            variable=self.chart_market_var,
            values=["NSE", "BSE", "NASDAQ", "NYSE", "LSE", "EURONEXT", "HKEX", "SSE", "SZSE"]
        )
        self.chart_market_option.grid(row=0, column=3, padx=5, pady=5)
        
        ctk.CTkLabel(input_frame, text="Period:").grid(row=0, column=4, padx=5, pady=5, sticky="w")
        self.period_var = ctk.StringVar(value="6mo")
        self.period_option = ctk.CTkOptionMenu(
            input_frame,
            variable=self.period_var,
            values=["1mo", "3mo", "6mo", "1y", "max"]
        )
        self.period_option.grid(row=0, column=5, padx=5, pady=5)
        
        display_button = ctk.CTkButton(input_frame, text="Analyze Stock", command=self.display_chart, fg_color="darkblue")
        display_button.grid(row=0, column=6, padx=10, pady=5)
        
        rec_frame = ctk.CTkFrame(frame)
        rec_frame.pack(padx=10, pady=10, fill="x")
        
        rec_title = ctk.CTkLabel(rec_frame, text="📊 Advanced Technical Analysis", font=("Arial", 14, "bold"))
        rec_title.pack(padx=10, pady=5)
        
        self.rec_text = ctk.CTkTextbox(rec_frame, height=150, font=("Courier", 12))
        self.rec_text.pack(padx=10, pady=5, fill="both", expand=True)
        self.rec_text.insert("1.0", "Enter ticker and market, then click 'Analyze Stock' for detailed recommendations.")
        self.rec_text.configure(state="disabled")
        
        chart_frame = ctk.CTkFrame(frame)
        chart_frame.pack(padx=10, pady=10, fill="both", expand=True)
        
        self.fig, self.ax = plt.subplots(figsize=(10, 5))
        self.ax.set_title("Stock Chart")
        self.ax.text(0.5, 0.5, "Enter ticker to display chart", ha='center', va='center', transform=self.ax.transAxes)
        self.ax.set_xticks([])
        self.ax.set_yticks([])
        
        self.canvas = FigureCanvasTkAgg(self.fig, master=chart_frame)
        self.canvas.draw()
        self.canvas.get_tk_widget().pack(fill="both", expand=True)
    
    def display_chart(self):
        ticker = self.chart_ticker_entry.get().strip()
        market = self.chart_market_var.get()
        period = self.period_var.get()
        
        if not ticker:
            messagebox.showwarning("Input Error", "Please enter a ticker.")
            return
        
        rec_data = self.stock_manager.advanced_recommendation(ticker, market)
        
        self.rec_text.configure(state="normal")
        self.rec_text.delete("1.0", "end")
        
        rec_text = f"RECOMMENDATION: {rec_data['recommendation']}\n"
        rec_text += f"{rec_data.get('score', '')}\n"
        rec_text += f"Current Price: ₹{rec_data.get('price', 'N/A')}\n\n"
        rec_text += "TECHNICAL SIGNALS:\n"
        for signal in rec_data['signals']:
            rec_text += f"  {signal}\n"
        
        self.rec_text.insert("1.0", rec_text)
        self.rec_text.configure(state="disabled")
        
        hist, full_ticker = self.stock_manager.get_stock_chart_data(ticker, market, period)
        if hist is None or hist.empty:
            messagebox.showerror("Error", f"No data available for {full_ticker}")
            return
        
        self.ax.clear()
        self.ax.plot(hist.index, hist['Close'], label='Close Price', color='blue', linewidth=2)
        
        if len(hist) >= 50:
            hist['SMA_50'] = hist['Close'].rolling(window=50).mean()
            self.ax.plot(hist.index, hist['SMA_50'], label='50-day MA', color='orange', linestyle='--')
        
        if len(hist) >= 200:
            hist['SMA_200'] = hist['Close'].rolling(window=200).mean()
            self.ax.plot(hist.index, hist['SMA_200'], label='200-day MA', color='red', linestyle='--')
        
        self.ax.set_title(f'{full_ticker} - Technical Chart ({period.upper()})', fontsize=14, fontweight='bold')
        self.ax.set_xlabel("Date")
        self.ax.set_ylabel("Price")
        self.ax.legend(loc='best')
        self.ax.grid(True, alpha=0.3)
        self.fig.tight_layout()
        self.canvas.draw()
    
    # ----------------- Analytics Content -----------------
    def create_analytics_content(self, frame):
        main_frame = ctk.CTkFrame(frame)
        main_frame.pack(padx=10, pady=10, fill="both", expand=True)
        
        top_frame = ctk.CTkFrame(main_frame)
        top_frame.pack(fill="x", pady=5)
        
        summary_box = ctk.CTkFrame(top_frame)
        summary_box.pack(side="left", fill="both", expand=True, padx=(0,5))
        summary_label_title = ctk.CTkLabel(summary_box, text="Portfolio Summary", font=("Arial", 14, "bold"))
        summary_label_title.pack(pady=(10,5))
        self.summary_label = ctk.CTkLabel(summary_box, text="Loading summary...", font=("Arial", 12))
        self.summary_label.pack(pady=10)
        
        pie_box = ctk.CTkFrame(top_frame)
        pie_box.pack(side="left", fill="both", expand=True, padx=(5,0))
        pie_label_title = ctk.CTkLabel(pie_box, text="Portfolio Composition", font=("Arial", 14, "bold"))
        pie_label_title.pack(pady=(10,5))
        self.pie_fig, self.pie_ax = plt.subplots(figsize=(4,4))
        self.pie_ax.text(0.5, 0.5, "No data", horizontalalignment='center', verticalalignment='center')
        self.pie_canvas = FigureCanvasTkAgg(self.pie_fig, master=pie_box)
        self.pie_canvas.draw()
        self.pie_canvas.get_tk_widget().pack(fill="both", expand=True, padx=10, pady=10)
        
        sector_box = ctk.CTkFrame(main_frame)
        sector_box.pack(fill="x", pady=10)
        sector_title = ctk.CTkLabel(sector_box, text="📊 Sector Diversification", font=("Arial", 14, "bold"))
        sector_title.pack(pady=(10,5))
        self.sector_label = ctk.CTkLabel(sector_box, text="Loading sector data...", font=("Arial", 11))
        self.sector_label.pack(pady=10)
        
        table_box = ctk.CTkFrame(main_frame)
        table_box.pack(fill="both", expand=True, pady=10)
        table_title = ctk.CTkLabel(table_box, text="Profit/Loss Details", font=("Arial", 14, "bold"))
        table_title.pack(pady=(10,5))
        
        table_columns = ("Ticker", "Shares", "Buy Price", "Current Price", "Current Value", "P/L", "P/L %")
        self.pl_tree = ttk.Treeview(table_box, columns=table_columns, show="headings", height=8)
        for col in table_columns:
            self.pl_tree.heading(col, text=col)
            self.pl_tree.column(col, anchor="center", width=100)
        
        self.pl_tree.tag_configure('profit', background='#90EE90')
        self.pl_tree.tag_configure('loss', background='#FFB6C1')
        
        self.pl_tree.pack(fill="both", expand=True, padx=10, pady=10)
    
    # ----------------- Alerts Content -----------------
    def create_alerts_content(self, frame):
        title_label = ctk.CTkLabel(frame, text="🔔 Price Alerts Manager", font=("Arial", 16, "bold"))
        title_label.pack(pady=10)
        
        add_frame = ctk.CTkFrame(frame)
        add_frame.pack(padx=10, pady=10, fill="x")
        
        ctk.CTkLabel(add_frame, text="Ticker:").grid(row=0, column=0, padx=5, pady=5, sticky="w")
        self.alert_ticker_entry = ctk.CTkEntry(add_frame, width=100)
        self.alert_ticker_entry.grid(row=0, column=1, padx=5, pady=5)
        
        ctk.CTkLabel(add_frame, text="Target Price:").grid(row=0, column=2, padx=5, pady=5, sticky="w")
        self.alert_price_entry = ctk.CTkEntry(add_frame, width=100)
        self.alert_price_entry.grid(row=0, column=3, padx=5, pady=5)
        
        ctk.CTkLabel(add_frame, text="Alert Type:").grid(row=0, column=4, padx=5, pady=5, sticky="w")
        self.alert_type_var = ctk.StringVar(value="above")
        self.alert_type_option = ctk.CTkOptionMenu(add_frame, variable=self.alert_type_var, values=["above", "below"])
        self.alert_type_option.grid(row=0, column=5, padx=5, pady=5)
        
        add_alert_btn = ctk.CTkButton(add_frame, text="Add Alert", command=self.add_price_alert, fg_color="green")
        add_alert_btn.grid(row=0, column=6, padx=10, pady=5)
        
        delete_alert_btn = ctk.CTkButton(add_frame, text="Delete Selected", command=self.delete_selected_alert, fg_color="red")
        delete_alert_btn.grid(row=0, column=7, padx=10, pady=5)
        
        alerts_frame = ctk.CTkFrame(frame)
        alerts_frame.pack(padx=10, pady=10, fill="both", expand=True)
        
        columns = ("Ticker", "Target Price", "Alert Type", "Created Date")
        self.alerts_tree = ttk.Treeview(alerts_frame, columns=columns, show="headings", height=15)
        for col in columns:
            self.alerts_tree.heading(col, text=col)
            self.alerts_tree.column(col, anchor="center", width=150)
        self.alerts_tree.pack(fill="both", expand=True, padx=10, pady=10)
    
    # ----------------- Performance Content -----------------
    def create_performance_content(self, frame):
        title_label = ctk.CTkLabel(frame, text="📈 Historical Performance Tracking", font=("Arial", 16, "bold"))
        title_label.pack(pady=10)
        
        info_frame = ctk.CTkFrame(frame)
        info_frame.pack(padx=10, pady=5, fill="x")
        self.perf_info_label = ctk.CTkLabel(info_frame, text="Performance data will be logged daily", font=("Arial", 11))
        self.perf_info_label.pack(pady=5)
        
        chart_frame = ctk.CTkFrame(frame)
        chart_frame.pack(padx=10, pady=10, fill="both", expand=True)
        
        self.perf_fig, (self.perf_ax1, self.perf_ax2) = plt.subplots(2, 1, figsize=(10, 6))
        self.perf_ax1.set_title("Portfolio Value Over Time")
        self.perf_ax2.set_title("Cumulative Profit/Loss Over Time")
        
        self.perf_canvas = FigureCanvasTkAgg(self.perf_fig, master=chart_frame)
        self.perf_canvas.draw()
        self.perf_canvas.get_tk_widget().pack(fill="both", expand=True)
    
    # ----------------- Tariff Impact Content -----------------
    def create_tariffs_content(self, frame):
        title_label = ctk.CTkLabel(frame, text="🌍 Tariff Impact Analysis", font=("Arial", 16, "bold"))
        title_label.pack(pady=10)
        
        add_frame = ctk.CTkFrame(frame)
        add_frame.pack(padx=10, pady=10, fill="x")
        
        ctk.CTkLabel(add_frame, text="Add Tariff Event", font=("Arial", 12, "bold")).grid(row=0, column=0, columnspan=4, pady=5)
        
        ctk.CTkLabel(add_frame, text="Source Country:").grid(row=1, column=0, padx=5, pady=5, sticky="w")
        self.tariff_source_entry = ctk.CTkEntry(add_frame, width=100)
        self.tariff_source_entry.grid(row=1, column=1, padx=5, pady=5)
        
        ctk.CTkLabel(add_frame, text="Target Country:").grid(row=1, column=2, padx=5, pady=5, sticky="w")
        self.tariff_target_entry = ctk.CTkEntry(add_frame, width=100)
        self.tariff_target_entry.grid(row=1, column=3, padx=5, pady=5)
        
        ctk.CTkLabel(add_frame, text="Affected Sectors (comma-separated):").grid(row=2, column=0, padx=5, pady=5, sticky="w")
        self.tariff_sectors_entry = ctk.CTkEntry(add_frame, width=300)
        self.tariff_sectors_entry.grid(row=2, column=1, columnspan=3, padx=5, pady=5)
        
        ctk.CTkLabel(add_frame, text="Tariff Rate (%):").grid(row=3, column=0, padx=5, pady=5, sticky="w")
        self.tariff_rate_entry = ctk.CTkEntry(add_frame, width=100)
        self.tariff_rate_entry.grid(row=3, column=1, padx=5, pady=5)
        
        ctk.CTkLabel(add_frame, text="Date (YYYY-MM-DD):").grid(row=3, column=2, padx=5, pady=5, sticky="w")
        self.tariff_date_entry = ctk.CTkEntry(add_frame, width=100)
        self.tariff_date_entry.insert(0, datetime.now().strftime("%Y-%m-%d"))
        self.tariff_date_entry.grid(row=3, column=3, padx=5, pady=5)
        
        ctk.CTkLabel(add_frame, text="Description:").grid(row=4, column=0, padx=5, pady=5, sticky="w")
        self.tariff_desc_entry = ctk.CTkEntry(add_frame, width=400)
        self.tariff_desc_entry.grid(row=4, column=1, columnspan=3, padx=5, pady=5)
        
        btn_frame = ctk.CTkFrame(add_frame)
        btn_frame.grid(row=5, column=0, columnspan=4, pady=10)
        
        add_tariff_btn = ctk.CTkButton(btn_frame, text="Add Tariff Event", command=self.add_tariff_event, fg_color="orange")
        add_tariff_btn.pack(side="left", padx=5)
        
        delete_tariff_btn = ctk.CTkButton(btn_frame, text="Delete Selected Event", command=self.delete_tariff_event, fg_color="red")
        delete_tariff_btn.pack(side="left", padx=5)
        
        analyze_btn = ctk.CTkButton(btn_frame, text="🔍 Analyze Portfolio Impact", command=self.analyze_portfolio_tariffs, fg_color="darkblue")
        analyze_btn.pack(side="left", padx=5)
        
        events_frame = ctk.CTkFrame(frame)
        events_frame.pack(padx=10, pady=10, fill="both", expand=True)
        
        ctk.CTkLabel(events_frame, text="Tariff Events Database", font=("Arial", 12, "bold")).pack(pady=5)
        
        columns = ("ID", "Source", "Target", "Sectors", "Rate %", "Date", "Description")
        self.tariff_events_tree = ttk.Treeview(events_frame, columns=columns, show="headings", height=8)
        for col in columns:
            self.tariff_events_tree.heading(col, text=col)
            width = 150 if col == "Description" else 80
            self.tariff_events_tree.column(col, anchor="center", width=width)
        self.tariff_events_tree.pack(fill="both", expand=True, padx=10, pady=5)
        
        impact_frame = ctk.CTkFrame(frame)
        impact_frame.pack(padx=10, pady=10, fill="both", expand=True)
        
        ctk.CTkLabel(impact_frame, text="Portfolio Tariff Exposure Analysis", font=("Arial", 12, "bold")).pack(pady=5)
        
        self.tariff_impact_text = ctk.CTkTextbox(impact_frame, height=200, font=("Courier", 12))
        self.tariff_impact_text.pack(padx=10, pady=5, fill="both", expand=True)
        self.tariff_impact_text.insert("1.0", "Click 'Analyze Portfolio Impact' to see detailed tariff exposure analysis for your holdings.")
        self.tariff_impact_text.configure(state="disabled")
    
    # ----------------- Green Bonds Content -----------------
    def create_green_bonds_content(self, frame):
        title_label = ctk.CTkLabel(frame, text="🌱 Green Bonds Tracker & ESG Analysis", font=("Arial", 16, "bold"))
        title_label.pack(pady=10)
        
        # Add Bond Form
        add_frame = ctk.CTkScrollableFrame(frame, height=220)
        add_frame.pack(padx=10, pady=10, fill="x")
        
        add_frame.grid_columnconfigure(1, weight=1)
        add_frame.grid_columnconfigure(3, weight=1)
        add_frame.grid_columnconfigure(5, weight=1)

        ctk.CTkLabel(add_frame, text="Add Green Bond", font=("Arial", 12, "bold")).grid(row=0, column=0, columnspan=6, pady=5)
        
        ctk.CTkLabel(add_frame, text="Issuer:").grid(row=1, column=0, padx=5, pady=5, sticky="w")
        self.gb_issuer_entry = ctk.CTkEntry(add_frame)
        self.gb_issuer_entry.grid(row=1, column=1, padx=5, pady=5, sticky="ew")
        
        ctk.CTkLabel(add_frame, text="Bond Name:").grid(row=1, column=2, padx=5, pady=5, sticky="w")
        self.gb_name_entry = ctk.CTkEntry(add_frame)
        self.gb_name_entry.grid(row=1, column=3, padx=5, pady=5, sticky="ew")
        
        ctk.CTkLabel(add_frame, text="ISIN:").grid(row=1, column=4, padx=5, pady=5, sticky="w")
        self.gb_isin_entry = ctk.CTkEntry(add_frame)
        self.gb_isin_entry.grid(row=1, column=5, padx=5, pady=5, sticky="ew")
        
        ctk.CTkLabel(add_frame, text="Coupon Rate (%):").grid(row=2, column=0, padx=5, pady=5, sticky="w")
        self.gb_coupon_entry = ctk.CTkEntry(add_frame)
        self.gb_coupon_entry.grid(row=2, column=1, padx=5, pady=5, sticky="ew")
        
        ctk.CTkLabel(add_frame, text="Current Yield (%):").grid(row=2, column=2, padx=5, pady=5, sticky="w")
        self.gb_yield_entry = ctk.CTkEntry(add_frame)
        self.gb_yield_entry.grid(row=2, column=3, padx=5, pady=5, sticky="ew")
        
        ctk.CTkLabel(add_frame, text="Maturity Date:").grid(row=2, column=4, padx=5, pady=5, sticky="w")
        self.gb_maturity_entry = ctk.CTkEntry(add_frame)
        self.gb_maturity_entry.insert(0, "YYYY-MM-DD")
        self.gb_maturity_entry.grid(row=2, column=5, padx=5, pady=5, sticky="ew")
        
        ctk.CTkLabel(add_frame, text="Issue Size:").grid(row=3, column=0, padx=5, pady=5, sticky="w")
        self.gb_size_entry = ctk.CTkEntry(add_frame)
        self.gb_size_entry.grid(row=3, column=1, padx=5, pady=5, sticky="ew")
        
        ctk.CTkLabel(add_frame, text="Currency:").grid(row=3, column=2, padx=5, pady=5, sticky="w")
        self.gb_currency_var = ctk.StringVar(value="INR")
        self.gb_currency_option = ctk.CTkOptionMenu(add_frame, variable=self.gb_currency_var, 
                                                      values=["INR", "USD", "EUR", "GBP"])
        self.gb_currency_option.grid(row=3, column=3, padx=5, pady=5, sticky="ew")
        
        ctk.CTkLabel(add_frame, text="Credit Rating:").grid(row=3, column=4, padx=5, pady=5, sticky="w")
        self.gb_rating_var = ctk.StringVar(value="A")
        self.gb_rating_option = ctk.CTkOptionMenu(add_frame, variable=self.gb_rating_var,
                                                    values=["AAA", "AA+", "AA", "AA-", "A+", "A", "A-", 
                                                           "BBB+", "BBB", "BBB-", "BB+", "BB"])
        self.gb_rating_option.grid(row=3, column=5, padx=5, pady=5, sticky="ew")
        
        ctk.CTkLabel(add_frame, text="Green Category:").grid(row=4, column=0, padx=5, pady=5, sticky="w")
        self.gb_category_var = ctk.StringVar(value="Renewable Energy")
        self.gb_category_option = ctk.CTkOptionMenu(add_frame, variable=self.gb_category_var,
                                                      values=["Renewable Energy", "Green Buildings", 
                                                             "Clean Transportation", "Water Management",
                                                             "Pollution Prevention", "Sustainable Agriculture",
                                                             "Biodiversity", "Climate Adaptation"])
        self.gb_category_option.grid(row=4, column=1, columnspan=2, padx=5, pady=5, sticky="ew")
        
        ctk.CTkLabel(add_frame, text="ESG Impact:").grid(row=4, column=3, padx=5, pady=5, sticky="w")
        self.gb_impact_var = ctk.StringVar(value="High")
        self.gb_impact_option = ctk.CTkOptionMenu(add_frame, variable=self.gb_impact_var,
                                                    values=["High", "Medium", "Low"])
        self.gb_impact_option.grid(row=4, column=4, padx=5, pady=5, sticky="ew")
        
        ctk.CTkLabel(add_frame, text="Purchase Amount:").grid(row=5, column=0, padx=5, pady=5, sticky="w")
        self.gb_purchase_entry = ctk.CTkEntry(add_frame)
        self.gb_purchase_entry.grid(row=5, column=1, padx=5, pady=5, sticky="ew")
        
        btn_frame = ctk.CTkFrame(add_frame)
        btn_frame.grid(row=6, column=0, columnspan=6, pady=10)
        
        add_bond_btn = ctk.CTkButton(btn_frame, text="Add Green Bond", command=self.add_green_bond, fg_color="#2ecc71")
        add_bond_btn.pack(side="left", padx=5)
        
        delete_bond_btn = ctk.CTkButton(btn_frame, text="Delete Selected", command=self.delete_green_bond, fg_color="red")
        delete_bond_btn.pack(side="left", padx=5)
        
        analyze_bond_btn = ctk.CTkButton(btn_frame, text="📊 Analyze Portfolio", command=self.analyze_green_bonds, fg_color="darkblue")
        analyze_bond_btn.pack(side="left", padx=5)
        
        # Bonds Table
        bonds_frame = ctk.CTkFrame(frame)
        bonds_frame.pack(padx=10, pady=10, fill="both", expand=True)
        
        ctk.CTkLabel(bonds_frame, text="Green Bonds Portfolio", font=("Arial", 12, "bold")).pack(pady=5)
        
        columns = ("ID", "Issuer", "Bond Name", "Coupon %", "Yield %", "Rating", "Category", "ESG Impact", "Score")
        self.bonds_tree = ttk.Treeview(bonds_frame, columns=columns, show="headings", height=8)
        for col in columns:
            self.bonds_tree.heading(col, text=col)
            width = 120 if col in ["Issuer", "Bond Name"] else 80
            self.bonds_tree.column(col, anchor="center", width=width)
        
        self.bonds_tree.tag_configure('excellent', background='#90EE90')
        self.bonds_tree.tag_configure('good', background='#FFFACD')
        self.bonds_tree.tag_configure('poor', background='#FFB6C1')
        
        self.bonds_tree.pack(fill="both", expand=True, padx=10, pady=5)
        
        # Analysis Display
        analysis_frame = ctk.CTkFrame(frame)
        analysis_frame.pack(padx=10, pady=10, fill="both", expand=True)
        
        ctk.CTkLabel(analysis_frame, text="Portfolio Analysis & Recommendations", font=("Arial", 12, "bold")).pack(pady=5)
        
        self.bonds_analysis_text = ctk.CTkTextbox(analysis_frame, height=200, font=("Courier", 12))
        self.bonds_analysis_text.pack(padx=10, pady=5, fill="both", expand=True)
        self.bonds_analysis_text.insert("1.0", "Add green bonds and click 'Analyze Portfolio' to see detailed ESG impact analysis and recommendations.")
        self.bonds_analysis_text.configure(state="disabled")
    
    def add_stock(self):
        ticker = self.ticker_entry.get().strip()
        shares_str = self.shares_entry.get().strip()
        buy_price_str = self.buy_price_entry.get().strip()
        market = self.market_var.get()
        
        if not ticker or not shares_str or not buy_price_str:
            messagebox.showwarning("Input Error", "Please fill in all fields.")
            return
        
        try:
            shares = float(shares_str)
            buy_price = float(buy_price_str)
            if shares <= 0 or buy_price <= 0:
                raise ValueError("Values must be positive")
        except ValueError as e:
            messagebox.showwarning("Input Error", f"Invalid input: {e}")
            return
        
        self.stock_manager.add_stock(ticker, shares, buy_price, market)
        messagebox.showinfo("Success", f"Added {get_full_ticker(ticker, market)} ({market}) to portfolio.")
        self.ticker_entry.delete(0, tk.END)
        self.shares_entry.delete(0, tk.END)
        self.buy_price_entry.delete(0, tk.END)
        self.update_portfolio_display()
    
    def delete_stock(self):
        selected = self.portfolio_tree.selection()
        if not selected:
            messagebox.showwarning("Selection Error", "Please select a stock to delete.")
            return
        
        for item in selected:
            values = self.portfolio_tree.item(item, "values")
            full_ticker = values[1]
            self.stock_manager.delete_stock(full_ticker)
        
        messagebox.showinfo("Success", "Selected stock(s) deleted.")
        self.update_portfolio_display()
    
    def update_portfolio_display(self):
        for row in self.portfolio_tree.get_children():
            self.portfolio_tree.delete(row)

        count = 1
        for full_ticker, data in self.stock_manager.portfolio.items():
            live_price = self.stock_manager.fetch_live_price(full_ticker)
            market = data['market']
            currency = CURRENCY_MAP.get(market, "INR")
            fx_rate = get_fx_rate_to_inr(currency)

            if live_price is None:
                current_price = "N/A"
                profit_loss = "N/A"
                pl_percent = "N/A"
                tag = 'neutral'
            else:
                price_in_inr = live_price * fx_rate
                current_price = f"₹{price_in_inr:.2f}"
                profit_loss_val = (price_in_inr - data['buy_price']) * data['shares']
                profit_loss = f"₹{profit_loss_val:.2f}"
                pl_percent_val = ((price_in_inr - data['buy_price']) / data['buy_price'] * 100)
                pl_percent = f"{pl_percent_val:.2f}%"
                
                if profit_loss_val > 0:
                    tag = 'profit'
                elif profit_loss_val < 0:
                    tag = 'loss'
                else:
                    tag = 'neutral'
                
                alerts_triggered = self.stock_manager.alert_manager.check_alerts(full_ticker, price_in_inr)
                for alert in alerts_triggered:
                    messagebox.showinfo("🔔 Alert Triggered!", 
                                      f"{full_ticker} reached {alert['type']} ₹{alert['target_price']}\n"
                                      f"Current Price: ₹{price_in_inr:.2f}")

            self.portfolio_tree.insert(
                "",
                tk.END,
                values=(
                    count,
                    full_ticker,
                    market,
                    data['shares'],
                    f"₹{data['buy_price']:.2f}",
                    current_price,
                    profit_loss,
                    pl_percent
                ),
                tags=(tag,)
            )
            count += 1
    
    def update_analytics(self):
        total_value = 0
        total_pl = 0
        pl_data = []
        labels = []
        sizes = []
        sector_data = {}

        for full_ticker, data in self.stock_manager.portfolio.items():
            live_price = self.stock_manager.fetch_live_price(full_ticker)
            if live_price is None:
                continue
            
            market = data['market']
            currency = CURRENCY_MAP.get(market, "INR")
            fx_rate = get_fx_rate_to_inr(currency)
            shares = data['shares']
            buy_price_inr = data['buy_price']
            current_value_inr = live_price * fx_rate * shares
            pl_inr = (live_price * fx_rate - buy_price_inr) * shares
            pl_percent = ((live_price * fx_rate - buy_price_inr) / buy_price_inr * 100) if buy_price_inr != 0 else 0

            total_value += current_value_inr
            total_pl += pl_inr
            labels.append(full_ticker)
            sizes.append(current_value_inr)
            
            info = self.stock_manager.get_stock_info(full_ticker)
            sector = info.get('sector', 'Unknown')
            if sector in sector_data:
                sector_data[sector] += current_value_inr
            else:
                sector_data[sector] = current_value_inr

            tag = 'profit' if pl_inr > 0 else 'loss'
            pl_data.append({
                "Ticker": full_ticker,
                "Shares": shares,
                "Buy Price": f"₹{buy_price_inr:.2f}",
                "Current Price": f"₹{live_price*fx_rate:.2f}",
                "Current Value": f"₹{current_value_inr:.2f}",
                "P/L": f"₹{pl_inr:.2f}",
                "P/L %": f"{pl_percent:.2f}%",
                "tag": tag
            })

        summary_text = f"Total Portfolio Value: ₹{total_value:,.2f}\n"
        summary_text += f"Total Profit/Loss: ₹{total_pl:,.2f}\n"
        pl_percent_total = (total_pl / (total_value - total_pl) * 100) if (total_value - total_pl) != 0 else 0
        summary_text += f"Total Return: {pl_percent_total:.2f}%"
        self.summary_label.configure(text=summary_text)

        self.pie_ax.clear()
        if sizes:
            self.pie_ax.pie(sizes, labels=labels, autopct='%1.1f%%', startangle=140)
            self.pie_ax.axis('equal')
        else:
            self.pie_ax.text(0.5, 0.5, "No data", ha='center', va='center')
        self.pie_canvas.draw()
        
        if sector_data:
            sector_text = "Sector Allocation:\n"
            for sector, value in sorted(sector_data.items(), key=lambda x: x[1], reverse=True):
                percentage = (value / total_value * 100) if total_value > 0 else 0
                sector_text += f"  • {sector}: ₹{value:,.2f} ({percentage:.1f}%)\n"
            self.sector_label.configure(text=sector_text)
        else:
            self.sector_label.configure(text="No sector data available")

        for row in self.pl_tree.get_children():
            self.pl_tree.delete(row)
        for item in pl_data:
            self.pl_tree.insert("", tk.END, values=(
                item["Ticker"],
                item["Shares"],
                item["Buy Price"],
                item["Current Price"],
                item["Current Value"],
                item["P/L"],
                item["P/L %"]
            ), tags=(item["tag"],))
        
        log_performance(total_value, total_pl)
    
    def add_price_alert(self):
        ticker = self.alert_ticker_entry.get().strip()
        price_str = self.alert_price_entry.get().strip()
        alert_type = self.alert_type_var.get()
        
        if not ticker or not price_str:
            messagebox.showwarning("Input Error", "Please enter ticker and target price.")
            return
        
        try:
            target_price = float(price_str)
            if target_price <= 0:
                raise ValueError("Price must be positive")
        except ValueError as e:
            messagebox.showwarning("Input Error", f"Invalid price: {e}")
            return
        
        self.stock_manager.alert_manager.add_alert(ticker.upper(), target_price, alert_type)
        messagebox.showinfo("Success", f"Alert added for {ticker.upper()}")
        self.alert_ticker_entry.delete(0, tk.END)
        self.alert_price_entry.delete(0, tk.END)
        self.refresh_alerts_display()
    
    def delete_selected_alert(self):
        selected = self.alerts_tree.selection()
        if not selected:
            messagebox.showwarning("Selection Error", "Please select an alert to delete.")
            return
        
        for item in selected:
            values = self.alerts_tree.item(item, "values")
            ticker = values[0]
            if ticker in self.stock_manager.alert_manager.alerts:
                if len(self.stock_manager.alert_manager.alerts[ticker]) > 0:
                    self.stock_manager.alert_manager.remove_alert(ticker, 0)
        
        messagebox.showinfo("Success", "Alert(s) deleted.")
        self.refresh_alerts_display()
    
    def refresh_alerts_display(self):
        for row in self.alerts_tree.get_children():
            self.alerts_tree.delete(row)
        
        for ticker, alerts in self.stock_manager.alert_manager.alerts.items():
            for alert in alerts:
                self.alerts_tree.insert("", tk.END, values=(
                    ticker,
                    f"₹{alert['target_price']:.2f}",
                    alert['type'].upper(),
                    alert['created']
                ))
    
    def check_alerts_background(self):
        def check():
            import time
            while True:
                try:
                    for full_ticker in self.stock_manager.portfolio.keys():
                        live_price = self.stock_manager.fetch_live_price(full_ticker)
                        if live_price:
                            market = self.stock_manager.portfolio[full_ticker]['market']
                            currency = CURRENCY_MAP.get(market, "INR")
                            fx_rate = get_fx_rate_to_inr(currency)
                            price_inr = live_price * fx_rate
                            
                            alerts_triggered = self.stock_manager.alert_manager.check_alerts(full_ticker, price_inr)
                            for alert in alerts_triggered:
                                self.after(0, lambda t=full_ticker, a=alert, p=price_inr: 
                                         messagebox.showinfo("🔔 Alert Triggered!", 
                                                           f"{t} reached {a['type']} ₹{a['target_price']}\n"
                                                           f"Current Price: ₹{p:.2f}"))
                except Exception as e:
                    print(f"Alert check error: {e}")
                
                time.sleep(300)
        
        threading.Thread(target=check, daemon=True).start()
    
    def update_performance_chart(self):
        try:
            df = pd.read_csv(PERFORMANCE_CSV)
            if df.empty or len(df) < 2:
                self.perf_info_label.configure(text="Not enough performance data yet. Data is logged daily.")
                return
            
            df['Date'] = pd.to_datetime(df['Date'])
            
            self.perf_ax1.clear()
            self.perf_ax2.clear()
            
            self.perf_ax1.plot(df['Date'], df['Total Value INR'], marker='o', linewidth=2, color='blue')
            self.perf_ax1.set_title("Portfolio Value Over Time", fontsize=12, fontweight='bold')
            self.perf_ax1.set_xlabel("Date")
            self.perf_ax1.set_ylabel("Value (INR)")
            self.perf_ax1.grid(True, alpha=0.3)
            self.perf_ax1.tick_params(axis='x', rotation=45)
            
            self.perf_ax2.plot(df['Date'], df['Total P/L INR'], marker='o', linewidth=2, color='green')
            self.perf_ax2.axhline(y=0, color='r', linestyle='--', alpha=0.5)
            self.perf_ax2.set_title("Cumulative Profit/Loss Over Time", fontsize=12, fontweight='bold')
            self.perf_ax2.set_xlabel("Date")
            self.perf_ax2.set_ylabel("P/L (INR)")
            self.perf_ax2.grid(True, alpha=0.3)
            self.perf_ax2.tick_params(axis='x', rotation=45)
            
            self.perf_fig.tight_layout()
            self.perf_canvas.draw()
            
            days_tracked = len(df)
            start_value = df['Total Value INR'].iloc[0]
            current_value = df['Total Value INR'].iloc[-1]
            total_return = ((current_value - start_value) / start_value * 100) if start_value > 0 else 0
            
            info_text = f"Tracking Period: {days_tracked} days | "
            info_text += f"Starting Value: ₹{start_value:,.2f} | "
            info_text += f"Current Value: ₹{current_value:,.2f} | "
            info_text += f"Total Return: {total_return:.2f}%"
            self.perf_info_label.configure(text=info_text)
            
        except Exception as e:
            self.perf_info_label.configure(text=f"Error loading performance data: {e}")
    
    def add_tariff_event(self):
        source = self.tariff_source_entry.get().strip()
        target = self.tariff_target_entry.get().strip()
        sectors_str = self.tariff_sectors_entry.get().strip()
        rate_str = self.tariff_rate_entry.get().strip()
        date = self.tariff_date_entry.get().strip()
        description = self.tariff_desc_entry.get().strip()
        
        if not all([source, target, sectors_str, rate_str, date]):
            messagebox.showwarning("Input Error", "Please fill in all required fields.")
            return
        
        try:
            rate = float(rate_str)
            if rate < 0:
                raise ValueError("Rate must be positive")
        except ValueError as e:
            messagebox.showwarning("Input Error", f"Invalid tariff rate: {e}")
            return
        
        sectors = [s.strip() for s in sectors_str.split(",")]
        
        self.stock_manager.tariff_analyzer.add_tariff_event(
            source, target, sectors, rate, description, date
        )
        
        messagebox.showinfo("Success", f"Tariff event added: {source} → {target}")
        
        self.tariff_source_entry.delete(0, tk.END)
        self.tariff_target_entry.delete(0, tk.END)
        self.tariff_sectors_entry.delete(0, tk.END)
        self.tariff_rate_entry.delete(0, tk.END)
        self.tariff_date_entry.delete(0, tk.END)
        self.tariff_date_entry.insert(0, datetime.now().strftime("%Y-%m-%d"))
        self.tariff_desc_entry.delete(0, tk.END)
        
        self.refresh_tariff_display()
    
    def delete_tariff_event(self):
        selected = self.tariff_events_tree.selection()
        if not selected:
            messagebox.showwarning("Selection Error", "Please select an event to delete.")
            return
        
        for item in selected:
            values = self.tariff_events_tree.item(item, "values")
            event_id = int(values[0])
            self.stock_manager.tariff_analyzer.remove_event(event_id)
        
        messagebox.showinfo("Success", "Tariff event(s) deleted.")
        self.refresh_tariff_display()
    
    def refresh_tariff_display(self):
        for row in self.tariff_events_tree.get_children():
            self.tariff_events_tree.delete(row)
        
        for event in self.stock_manager.tariff_analyzer.events:
            sectors_display = ", ".join(event["affected_sectors"][:3])
            if len(event["affected_sectors"]) > 3:
                sectors_display += "..."
            
            self.tariff_events_tree.insert("", tk.END, values=(
                event["id"],
                event["source_country"],
                event["target_country"],
                sectors_display,
                f"{event['tariff_rate']}%",
                event["date"],
                event["description"][:50]
            ))
    
    def analyze_portfolio_tariffs(self):
        self.tariff_impact_text.configure(state="normal")
        self.tariff_impact_text.delete("1.0", "end")
        
        if not self.stock_manager.portfolio:
            self.tariff_impact_text.insert("1.0", "No stocks in portfolio to analyze.")
            self.tariff_impact_text.configure(state="disabled")
            return
        
        if not self.stock_manager.tariff_analyzer.events:
            self.tariff_impact_text.insert("1.0", "No tariff events in database. Add tariff events to analyze impact.")
            self.tariff_impact_text.configure(state="disabled")
            return
        
        analysis_text = "=" * 80 + "\n"
        analysis_text += "PORTFOLIO TARIFF EXPOSURE ANALYSIS\n"
        analysis_text += "=" * 80 + "\n\n"
        
        portfolio_data = []
        
        for full_ticker, data in self.stock_manager.portfolio.items():
            info = self.stock_manager.get_stock_info(full_ticker)
            sector = info.get('sector', 'Unknown')
            industry = info.get('industry', 'Unknown')
            market = data['market']
            
            tariff_analysis = self.stock_manager.tariff_analyzer.analyze_stock_exposure(
                full_ticker, market, sector, industry
            )
            
            portfolio_data.append({
                "ticker": full_ticker,
                "sector": sector,
                "tariff_analysis": tariff_analysis,
                "shares": data['shares']
            })
        
        summary = self.stock_manager.tariff_analyzer.get_portfolio_tariff_summary(portfolio_data)
        
        analysis_text += f"📊 PORTFOLIO SUMMARY:\n"
        analysis_text += f"   Total Tariff Exposure Score: {summary['total_exposure_score']}\n"
        analysis_text += f"   🔴 High Risk Stocks: {summary['high_risk_count']}\n"
        analysis_text += f"   🟡 Moderate Risk Stocks: {summary['moderate_risk_count']}\n"
        analysis_text += f"   🟢 Low Risk Stocks: {summary['low_risk_count']}\n\n"
        
        analysis_text += "=" * 80 + "\n"
        analysis_text += "INDIVIDUAL STOCK ANALYSIS:\n"
        analysis_text += "=" * 80 + "\n\n"
        
        portfolio_data.sort(key=lambda x: x['tariff_analysis']['impact_score'], reverse=True)
        
        for stock in portfolio_data:
            analysis = stock['tariff_analysis']
            analysis_text += f"📌 {stock['ticker']}\n"
            analysis_text += f"   Sector: {analysis['sector']}\n"
            analysis_text += f"   Country: {analysis['stock_country']}\n"
            analysis_text += f"   Risk Level: {analysis['risk_level']}\n"
            analysis_text += f"   Impact Score: {analysis['impact_score']}\n"
            
            if analysis['affected_events']:
                analysis_text += f"   \n   ⚠️  AFFECTED BY {len(analysis['affected_events'])} TARIFF EVENT(S):\n"
                for i, affected in enumerate(analysis['affected_events'], 1):
                    event = affected['event']
                    analysis_text += f"   \n   Event {i}: {event['source_country']} → {event['target_country']}\n"
                    analysis_text += f"      Tariff Rate: {event['tariff_rate']}%\n"
                    analysis_text += f"      Date: {event['date']}\n"
                    analysis_text += f"      Description: {event['description']}\n"
                    analysis_text += f"      Impact Reasons:\n"
                    for reason in affected['reasons']:
                        analysis_text += f"         • {reason}\n"
            else:
                analysis_text += f"   ✅ No tariff impact detected\n"
            
            analysis_text += "\n" + "-" * 80 + "\n\n"
        
        analysis_text += "=" * 80 + "\n"
        analysis_text += "💡 RECOMMENDATIONS:\n"
        analysis_text += "=" * 80 + "\n\n"
        
        if summary['high_risk_count'] > 0:
            analysis_text += "🔴 HIGH RISK STOCKS - Consider the following actions:\n"
            for stock in summary['high_risk_stocks']:
                analysis_text += f"   • {stock['ticker']}: Monitor closely for price volatility\n"
                analysis_text += f"     Consider diversifying exposure or setting stop-loss orders\n"
            analysis_text += "\n"
        
        if summary['moderate_risk_count'] > 0:
            analysis_text += "🟡 MODERATE RISK STOCKS - Stay informed:\n"
            for stock in summary['moderate_risk_stocks']:
                analysis_text += f"   • {stock['ticker']}: Watch for supply chain disruptions\n"
            analysis_text += "\n"
        
        if summary['total_exposure_score'] > 50:
            analysis_text += "⚠️  HIGH PORTFOLIO EXPOSURE: Your portfolio has significant tariff exposure.\n"
            analysis_text += "   Consider rebalancing towards sectors/regions with lower tariff risk.\n\n"
        elif summary['total_exposure_score'] > 25:
            analysis_text += "⚡ MODERATE PORTFOLIO EXPOSURE: Monitor tariff developments regularly.\n\n"
        else:
            analysis_text += "✅ LOW PORTFOLIO EXPOSURE: Your portfolio is well-positioned against tariffs.\n\n"
        
        self.tariff_impact_text.insert("1.0", analysis_text)
        self.tariff_impact_text.configure(state="disabled")
    
    # Green Bonds Functions
    def add_green_bond(self):
        issuer = self.gb_issuer_entry.get().strip()
        bond_name = self.gb_name_entry.get().strip()
        isin = self.gb_isin_entry.get().strip()
        coupon_str = self.gb_coupon_entry.get().strip()
        yield_str = self.gb_yield_entry.get().strip()
        maturity = self.gb_maturity_entry.get().strip()
        size_str = self.gb_size_entry.get().strip()
        currency = self.gb_currency_var.get()
        rating = self.gb_rating_var.get()
        category = self.gb_category_var.get()
        impact = self.gb_impact_var.get()
        purchase_str = self.gb_purchase_entry.get().strip()
        
        if not all([issuer, bond_name, coupon_str, yield_str, maturity, purchase_str]):
            messagebox.showwarning("Input Error", "Please fill in all required fields.")
            return
        
        try:
            coupon_rate = float(coupon_str)
            current_yield = float(yield_str)
            issue_size = float(size_str) if size_str else 0
            purchase_amount = float(purchase_str)
            
            if coupon_rate < 0 or current_yield < 0 or purchase_amount <= 0:
                raise ValueError("Values must be positive")
        except ValueError as e:
            messagebox.showwarning("Input Error", f"Invalid input: {e}")
            return
        
        self.stock_manager.green_bonds_tracker.add_bond(
            issuer, bond_name, isin, coupon_rate, maturity, issue_size,
            currency, rating, category, impact, current_yield, purchase_amount
        )
        
        messagebox.showinfo("Success", f"Green bond added: {bond_name}")
        
        # Clear fields
        self.gb_issuer_entry.delete(0, tk.END)
        self.gb_name_entry.delete(0, tk.END)
        self.gb_isin_entry.delete(0, tk.END)
        self.gb_coupon_entry.delete(0, tk.END)
        self.gb_yield_entry.delete(0, tk.END)
        self.gb_maturity_entry.delete(0, tk.END)
        self.gb_maturity_entry.insert(0, "YYYY-MM-DD")
        self.gb_size_entry.delete(0, tk.END)
        self.gb_purchase_entry.delete(0, tk.END)
        
        self.refresh_green_bonds_display()
    
    def delete_green_bond(self):
        selected = self.bonds_tree.selection()
        if not selected:
            messagebox.showwarning("Selection Error", "Please select a bond to delete.")
            return
        
        for item in selected:
            values = self.bonds_tree.item(item, "values")
            bond_id = int(values[0])
            self.stock_manager.green_bonds_tracker.remove_bond(bond_id)
        
        messagebox.showinfo("Success", "Green bond(s) deleted.")
        self.refresh_green_bonds_display()
    
    def refresh_green_bonds_display(self):
        for row in self.bonds_tree.get_children():
            self.bonds_tree.delete(row)
        
        for bond in self.stock_manager.green_bonds_tracker.bonds:
            score = self.stock_manager.green_bonds_tracker.calculate_bond_score(bond)
            
            # Determine color tag based on score
            if score >= 75:
                tag = 'excellent'
            elif score >= 50:
                tag = 'good'
            else:
                tag = 'poor'
            
            self.bonds_tree.insert("", tk.END, values=(
                bond["id"],
                bond["issuer"],
                bond["bond_name"],
                f"{bond['coupon_rate']}%",
                f"{bond['current_yield']}%",
                bond["credit_rating"],
                bond["green_category"],
                bond["esg_impact"],
                f"{score:.0f}"
            ), tags=(tag,))
    
    def analyze_green_bonds(self):
        self.bonds_analysis_text.configure(state="normal")
        self.bonds_analysis_text.delete("1.0", "end")
        
        if not self.stock_manager.green_bonds_tracker.bonds:
            self.bonds_analysis_text.insert("1.0", "No green bonds in portfolio. Add bonds to see analysis.")
            self.bonds_analysis_text.configure(state="disabled")
            return
        
        analysis = self.stock_manager.green_bonds_tracker.get_portfolio_analysis()
        
        analysis_text = "=" * 80 + "\n"
        analysis_text += "GREEN BONDS PORTFOLIO ANALYSIS\n"
        analysis_text += "=" * 80 + "\n\n"
        
        analysis_text += f"📊 PORTFOLIO OVERVIEW:\n"
        analysis_text += f"   Total Bonds: {analysis['total_bonds']}\n"
        analysis_text += f"   Total Investment: ₹{analysis['total_investment']:,.2f}\n"
        analysis_text += f"   Average Yield: {analysis['avg_yield']:.2f}%\n"
        analysis_text += f"   Average Quality Score: {analysis['avg_score']:.1f}/100\n\n"
        
        analysis_text += "=" * 80 + "\n"
        analysis_text += "ESG IMPACT DISTRIBUTION:\n"
        analysis_text += "=" * 80 + "\n\n"
        
        impact_dist = analysis['impact_distribution']
        total_bonds = analysis['total_bonds']
        analysis_text += f"   🟢 High Impact Bonds: {impact_dist['High']} ({impact_dist['High']/total_bonds*100:.1f}%)\n"
        analysis_text += f"   🟡 Medium Impact Bonds: {impact_dist['Medium']} ({impact_dist['Medium']/total_bonds*100:.1f}%)\n"
        analysis_text += f"   🟠 Low Impact Bonds: {impact_dist['Low']} ({impact_dist['Low']/total_bonds*100:.1f}%)\n\n"
        
        analysis_text += "=" * 80 + "\n"
        analysis_text += "GREEN CATEGORY ALLOCATION:\n"
        analysis_text += "=" * 80 + "\n\n"
        
        for category, amount in sorted(analysis['category_allocation'].items(), key=lambda x: x[1], reverse=True):
            percentage = (amount / analysis['total_investment'] * 100)
            analysis_text += f"   • {category}: ₹{amount:,.2f} ({percentage:.1f}%)\n"
        
        analysis_text += "\n" + "=" * 80 + "\n"
        analysis_text += "INDIVIDUAL BOND RECOMMENDATIONS:\n"
        analysis_text += "=" * 80 + "\n\n"
        
        sorted_bonds = sorted(self.stock_manager.green_bonds_tracker.bonds, 
                            key=lambda b: self.stock_manager.green_bonds_tracker.calculate_bond_score(b), 
                            reverse=True)
        
        for bond in sorted_bonds:
            rec = self.stock_manager.green_bonds_tracker.get_bond_recommendation(bond)
            
            analysis_text += f"📌 {bond['bond_name']} ({bond['issuer']})\n"
            analysis_text += f"   ISIN: {bond['isin']}\n"
            analysis_text += f"   Score: {rec['score']}/100\n"
            analysis_text += f"   {rec['recommendation']}\n\n"
            
            analysis_text += "   Analysis Details:\n"
            for detail in rec['details']:
                analysis_text += f"      {detail}\n"
            
            analysis_text += f"\n   Financial Metrics:\n"
            analysis_text += f"      Coupon Rate: {bond['coupon_rate']}%\n"
            analysis_text += f"      Current Yield: {bond['current_yield']}%\n"
            analysis_text += f"      Maturity: {bond['maturity_date']}\n"
            analysis_text += f"      Investment: ₹{bond['purchase_amount']:,.2f}\n"
            
            analysis_text += "\n" + "-" * 80 + "\n\n"
        
        analysis_text += "=" * 80 + "\n"
        analysis_text += "💡 PORTFOLIO RECOMMENDATIONS:\n"
        analysis_text += "=" * 80 + "\n\n"
        
        if analysis['avg_score'] >= 75:
            analysis_text += "✅ EXCELLENT PORTFOLIO: Your green bonds portfolio shows strong quality and ESG impact.\n"
        elif analysis['avg_score'] >= 60:
            analysis_text += "✓ GOOD PORTFOLIO: Solid green bond selection with good sustainability credentials.\n"
        elif analysis['avg_score'] >= 45:
            analysis_text += "⚠ MODERATE PORTFOLIO: Consider upgrading to higher-rated bonds or better ESG impact.\n"
        else:
            analysis_text += "⚠️ WEAK PORTFOLIO: Significant improvement needed in credit quality and ESG impact.\n"
        
        analysis_text += "\n"
        
        if analysis['avg_yield'] < 4:
            analysis_text += "• Yield Improvement: Current average yield is low. Consider bonds with better returns.\n"
        elif analysis['avg_yield'] > 8:
            analysis_text += "• High Yield Alert: Very high yields may indicate higher risk. Review credit ratings.\n"
        
        high_impact_pct = (impact_dist['High'] / total_bonds * 100)
        if high_impact_pct < 50:
            analysis_text += "• ESG Enhancement: Increase allocation to High Impact bonds for better sustainability.\n"
        
        category_count = len(analysis['category_allocation'])
        if category_count < 3:
            analysis_text += "• Diversification: Consider spreading investments across more green categories.\n"
        
        analysis_text += "\n" + "=" * 80 + "\n"
        analysis_text += "SUSTAINABILITY IMPACT SUMMARY:\n"
        analysis_text += "=" * 80 + "\n\n"
        
        analysis_text += "Your green bond investments support the following UN Sustainable Development Goals:\n\n"
        
        for category in analysis['category_allocation'].keys():
            if "Renewable Energy" in category:
                analysis_text += "   🌞 SDG 7: Affordable and Clean Energy\n"
            elif "Green Building" in category:
                analysis_text += "   🏢 SDG 11: Sustainable Cities and Communities\n"
            elif "Clean Transportation" in category:
                analysis_text += "   🚗 SDG 9: Industry, Innovation and Infrastructure\n"
            elif "Water" in category:
                analysis_text += "   💧 SDG 6: Clean Water and Sanitation\n"
            elif "Climate" in category:
                analysis_text += "   🌍 SDG 13: Climate Action\n"
            elif "Biodiversity" in category:
                analysis_text += "   🌳 SDG 15: Life on Land\n"
        
        analysis_text += "\n"
        total_impact = analysis['total_investment']
        analysis_text += f"Total Capital Allocated to Sustainable Development: ₹{total_impact:,.2f}\n"
        
        self.bonds_analysis_text.insert("1.0", analysis_text)
        self.bonds_analysis_text.configure(state="disabled")


if __name__ == "__main__":
    app = StockManagerGUI()
    app.mainloop()
