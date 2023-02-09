import os
from datetime import datetime
import pytz
from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd


# API KEY IEX: pk_57d08a7e22d04c858eb465d93ca0c0e7
# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")

# Make sure API key is set
if not os.environ.get("API_KEY"):
    raise RuntimeError("API_KEY not set")


@app.after_request
def after_request(response):
    """Ensure responses aren't cached"""
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""
    if request.method == "GET":
        ROW = db.execute(
            "select symbol,name,total_shares,price,total from total_shares where holder_id = ?", session["user_id"])
        index = 0
        while index < len(ROW):
            ROW[index]['price'] = usd(ROW[index]['price'])
            ROW[index]['total'] = usd(ROW[index]['total'])
            index += 1
        client_cash = db.execute(
            "select cash from users where id = ?", session["user_id"]
        )
        return render_template("index.html", rows=ROW, cash=usd(client_cash[0]["cash"]))


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""
    if request.method == "GET":
        return render_template("buy.html")
    else:
        total_price = 0
        symbol = request.form.get("symbol")
        if symbol.isalpha() is False:
            return apology("symbol must be a word", 400)
        symbol = symbol.upper()
        shares_number = request.form.get("shares")
        if shares_number.isdigit() is False:
            return apology("shares must be a number", 400)
        lookup_info = lookup(symbol)
        name = lookup_info["name"]
        if lookup_info is None:
            return apology("invalid symbol", 400)
        total_price = float(shares_number) * float(lookup_info["price"])
        client_cash = db.execute(
            "select cash from users where id = ?", session["user_id"]
        )
        if total_price > client_cash[0]["cash"]:
            return apology("you don't have enough cash", 400)
        newClientCash = client_cash[0]["cash"] - total_price
        bucharestTZ = pytz.timezone("Europe/Bucharest")
        timeInBucharest = datetime.now(bucharestTZ)
        db.execute(
            "INSERT INTO transactions (transactionerID, symbol, name, shares, price, total,transaction_time) VALUES (?,?,?,?,?,?,?)",
            session["user_id"],
            symbol,
            name,
            shares_number,
            float(lookup_info["price"]),
            total_price,
            timeInBucharest.strftime("%Y-%m-%d %H:%M:%S"),
        )
        total_shares = db.execute("SELECT sum(shares) as 'total_shares' from transactions where transactionerID = ? and symbol = ?",
                                  session["user_id"],
                                  symbol)
        total_price = float(
            total_shares[0]['total_shares']) * float(lookup_info["price"])
        count = db.execute(
            "select count(*) as 'count' from total_shares where symbol = ?", symbol)
        if count[0]['count'] == 0:
            db.execute(
                "INSERT INTO total_shares (holder_id, symbol, name, total_shares, price, total) VALUES (?,?,?,?,?,?)",
                session["user_id"],
                symbol,
                name,
                total_shares[0]['total_shares'],
                float(lookup_info["price"]),
                total_price,
            )
        else:
            db.execute(
                "UPDATE total_shares set total_shares = ? where symbol = ?",
                total_shares[0]['total_shares'],
                symbol
            )
        db.execute(
            "UPDATE users set cash = ? where id = ?", newClientCash, session["user_id"]
        )
        return redirect("/", code=302)


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""
    if request.method == "GET":
        ROW = db.execute(
            "select symbol,shares,price,transaction_time from transactions where transactionerID = ?", session["user_id"])
        index = 0
        while index < len(ROW):
            ROW[index]['price'] = usd(ROW[index]['price'])
            index += 1
        client_cash = db.execute(
            "select cash from users where id = ?", session["user_id"]
        )
        return render_template("history.html", rows=ROW, cash=usd(client_cash[0]["cash"]))


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute(
            "SELECT * FROM users WHERE username = ?", request.form.get(
                "username")
        )

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(
            rows[0]["hash"], request.form.get("password")
        ):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""
    if request.method == "GET":
        return render_template("quoted.html")
    else:
        quote = lookup(request.form.get("symbol"))
        if quote is not None:
            return render_template(
                "quote.html",
                company_name=quote["name"],
                symbol=quote["symbol"],
                price=usd(quote["price"]),
            )
        else:
            return apology("invalid symbol", 400)


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    session.clear()
    if request.method == "POST":
        if not request.form.get("username"):
            return apology("must provide username", 400)
        if not request.form.get("password"):
            return apology("must provide password", 400)
        if not request.form.get("confirmation"):
            return apology("password needs to match", 400)
        if request.form.get("password") != request.form.get("confirmation"):
            return apology("password needs to match", 400)
        rows = db.execute(
            "SELECT * FROM users WHERE username = ?", request.form.get(
                "username")
        )
        for row in rows:
            if row["username"] == request.form.get("username"):
                return apology("username already used", 400)
        username = request.form.get("username")
        password = request.form.get("password")
        db.execute(
            "INSERT INTO users(username,hash) VALUES (?,?)",
            username,
            generate_password_hash(password),
        )
        id = db.execute(
            "SELECT id from users where username =?", username)
        session["user_id"] = id
        return render_template("login.html")
    else:
        return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""
    if request.method == "GET":
        ROW = db.execute(
            "select symbol from transactions where transactionerID = ? group by symbol", session["user_id"])
        return render_template("sell.html", rows=ROW)

    else:
        symbol = request.form.get("symbol")
        if not symbol:
            return apology("choose what stock you want to sell", 403)
        number_shares_requested = request.form.get("shares")
        if number_shares_requested.isdigit() is False:
            return apology("invalid input", 400)
        transactionerID = session["user_id"]
        number_shares_client = db.execute(
            "select total_shares as 'total_shares' from total_shares where holder_id = ? and symbol = ?", transactionerID, symbol)
        if int(number_shares_requested) > number_shares_client[0]['total_shares']:
            return apology("not enough shares", 400)
        if int(number_shares_requested) - number_shares_client[0]['total_shares'] == 0:
            db.execute(
                "DELETE FROM total_shares where symbol = ? and holder_id = ?", symbol, transactionerID)
        new_client_stocks = number_shares_client[0]['total_shares'] - int(
            number_shares_requested)
        lookup_info = lookup(symbol)
        name = lookup_info["name"]
        new_client_total = new_client_stocks * lookup_info['price']
        total_price = float(number_shares_requested) * \
            float(lookup_info["price"])
        number_shares_requested = '-' + number_shares_requested
        bucharestTZ = pytz.timezone("Europe/Bucharest")
        timeInBucharest = datetime.now(bucharestTZ)
        db.execute(
            "UPDATE total_shares set total_shares = ?, total = ? where holder_id = ? and symbol = ?", new_client_stocks, new_client_total, transactionerID, symbol
        )
        db.execute(
            "INSERT INTO transactions (transactionerID, symbol, name, shares, price, total,transaction_time) VALUES (?,?,?,?,?,?,?)",
            session["user_id"],
            symbol,
            name,
            number_shares_requested,
            float(lookup_info["price"]),
            total_price,
            timeInBucharest.strftime("%Y-%m-%d %H:%M:%S"),
        )
        client_cash = db.execute(
            "select cash from users where id = ?", transactionerID)
        client_cash[0]['cash'] = client_cash[0]['cash'] + total_price
        db.execute(
            "UPDATE users set cash = ? where id = ?",
            client_cash[0]['cash'],
            transactionerID
        )
        return redirect("/", code=302)
