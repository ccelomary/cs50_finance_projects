import os

from cs50 import SQL
from flask import Flask, flash, jsonify, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions, HTTPException, InternalServerError
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd
from datetime import datetime as dt 

# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True

# Ensure responses aren't cached
@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_FILE_DIR"] = mkdtemp()
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")

# Make sure API key is set
if not os.environ.get("API_KEY"):
    raise RuntimeError("API_KEY not set")


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""
    row = db.execute('SELECT cash FROM users WHERE id=?', session['user_id'])
    cash = row[0]['cash']
    rows = db.execute('SELECT * FROM stock WHERE owner_id=?', session['user_id'])
    data = {'transactions': rows, 'cash': cash}
    return render_template('home.html', data=data)

@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""
    if request.method == 'POST':
        user_id = session.get('user_id')
        symbol = request.form.get('symbol')
        shares = int(request.form.get('shares'))
        if data:=lookup(symbol):
            price = data.get('price')
            total = price * shares
            name = data.get('name')
            row = db.execute("SELECT cash FROM users WHERE id=?", user_id)
            current_cash = row[0]['cash'] - total
            if current_cash < 0:
                return apology('insufficient funds')
            else:
                if st := db.execute('SELECT * FROM stock WHERE symbol=? AND owner_id=?', symbol, user_id):
                    shares = st[0]['shares'] + shares
                    total = round(st[0]['total'] + total, 3)
                    db.execute('UPDATE stock SET shares=?, total=?, price=? WHERE id=?', shares, total, price, st[0]['id'])
                else:
                    db.execute('INSERT INTO stock(symbol, name, price, shares, total, owner_id) VALUES (?,?,?,?,?,?)',
                    symbol, name, price, shares, total, user_id)
                db.execute('UPDATE users SET cash=? WHERE id=?', current_cash, user_id)
                db.execute('INSERT INTO transactions(symbol, shares, price, dt, owner_id) VALUES (?,?,?,?,?)',
                symbol, shares, price, dt.now(), session.get('user_id'))
                return redirect('/')
        else:
            return apology('INVALID SYMBOL!')
    return render_template("buy.html")


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""
    transactions = db.execute('SELECT * FROM transactions WHERE owner_id=?', session['user_id'])
    return render_template('history.html', transactions=transactions)

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
        rows = db.execute("SELECT * FROM users WHERE username = :username",
                          username=request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
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
    if request.method == 'POST':
        data = lookup(request.form.get('symbol'))
        return render_template('quote.html', data=data)
    return render_template("quote.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    if request.method == 'POST':
        data = dict((field.split('=') for field in request.get_data().decode().split('&')))
        for key, value in data.items():
            if not value:
                return apology("you must provide {} field".format(key), 403)
        if data['password'] != data['rpassword']:
            return apology('mismatch password', 403)
        try:
            id_ = db.execute('INSERT INTO users(username, hash) VALUES (?,?)', data['username'], generate_password_hash(data['password']))
        except RuntimeError:
            return apology('username is already used!', 403)
        session['user_id'] = id_
        return redirect('/')
    return render_template('register.html')


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""
    if request.method == 'POST':
        stock_id = request.form.get('selected_stock')
        shares = int(request.form.get('shares'))
        stock = db.execute('SELECT * FROM stock WHERE id=?', stock_id)[0]
        if stock.get('shares') < shares:
            return apology('Out of stock soory the maximum quantity is {}'.format(stock.get('shares')), 200)
        user = db.execute('SELECT cash FROM users WHERE id=?', session['user_id'])
        new_price = lookup(stock['symbol'])['price']
        cash = round(new_price * shares + user[0].get('cash'), 3)
        total = round(stock['total'] - new_price * shares, 3)
        sh = -shares
        shares = stock.get('shares') - shares
        db.execute('UPDATE users SET cash=? WHERE id=?', cash, session['user_id'])
        db.execute('UPDATE stock SET shares=?, total=? WHERE id=?', shares, total, stock_id)
        db.execute('INSERT INTO transactions(symbol, shares, price, dt, owner_id) VALUES (?,?,?,?,?)',
                stock.get('symbol'), sh, stock.get('price'), dt.now(), session.get('user_id'))
        return redirect('/')
    rows = db.execute('SELECT id, symbol FROM stock WHERE owner_id=?;', session['user_id'])
    return render_template('sell.html', rows=rows)


def errorhandler(e):
    """Handle error"""
    if not isinstance(e, HTTPException):
        e = InternalServerError()
    return apology(e.name, e.code)


# Listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)


if __name__ == '__main__':
    app.run()