from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session, url_for
from flask_session import Session
from passlib.apps import custom_app_context as pwd_context
from passlib.context import CryptContext # --> import the CryptContext class, used to handle all hashing...
from tempfile import mkdtemp
from datetime import datetime

from helpers import *

#
pwd_context = CryptContext(
    # hash supported
    schemes=["pbkdf2_sha256", "des_crypt" ],
    default="pbkdf2_sha256",

    # vary rounds parameter randomly when creating new hashes...
    all__vary_rounds = 0.1,

    # set the number of rounds that should be used...
    # (appropriate values may vary for different schemes,
    # and the amount of time you wish it to take)
    pbkdf2_sha256__default_rounds = 8000,
    )




# configure application
app = Flask(__name__)

# ensure responses aren't cached
if app.config["DEBUG"]:
    @app.after_request
    def after_request(response):
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Expires"] = 0
        response.headers["Pragma"] = "no-cache"
        return response

# custom filter
app.jinja_env.filters["usd"] = usd

# configure session to use filesystem (instead of signed cookies)
app.config["SESSION_FILE_DIR"] = mkdtemp()
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")


@app.route("/")
@login_required
def index():
    
    # select each stock symbol and ammount of shares from portfolio
    stocks = db.execute("SELECT shares, symbol FROM portfolio WHERE id = :id", id=session["user_id"])
    
    # keep track of share's worth
    total_cash = 0
    
    # iterate through stocks and update portfolio
    for stock in stocks:
        symbol = stock["symbol"]
        shares = stock["shares"]
        stock_info = lookup(symbol)
        total_value = shares * stock_info["price"]
        total_cash += total_value
        db.execute("UPDATE portfolio SET price=:price, total=:total WHERE id=:id AND symbol=:symbol", price=usd(stock_info["price"]), total=usd(total_value), id=session["user_id"], symbol=symbol)
        
    # update user's cash in portfolio
    new_cash = db.execute("SELECT cash FROM users WHERE id=:id", id=session["user_id"])
    
    # update grand total
    total_cash += new_cash[0]["cash"]
    
    # display current portfolio in index homepage
    new_portfolio = db.execute("SELECT * from portfolio WHERE id=:id", id=session["user_id"])
    
    return render_template("index.html", stocks=new_portfolio, cash=usd(new_cash[0]["cash"]), total=usd(total_cash))

@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock."""
    if request.method == "POST":
        
        # ensure user provide both values
        if not request.form.get("symbol") or not request.form.get("quantity"):
            return apology("Must provide symbol and quantity")
        
        # search for stock info
        stock_info = lookup(request.form.get("symbol"))
        
        # if no stocks are found, inform the user
        if not stock_info:
            return apology("invalid symbol")
            
        # ensure proper ammount of shares
        try:
            shares = int(request.form.get("quantity"))
            if not shares or shares < 0:
                return apology("wrong input")
        except:
            return apology("Wrong input")
        
        # calculate total price for stock
        total_cost = stock_info["price"] * shares
        
        # get name of stock
        name = stock_info["name"]
        
        # check if user has enough cash
        user_cash = db.execute("SELECT cash FROM users WHERE id = :id", id=session["user_id"])
        if not user_cash or float(user_cash[0]["cash"]) < total_cost:
            return apology("you do not have enough cash for this transaction")
        else:
            # subtract cost of shares from user's cash
            db.execute("UPDATE users SET cash = cash - :purchase WHERE id = :id", id=session["user_id"], purchase=stock_info["price"] * float(shares))
            
            # update cash info
            #db.execute("UPDATE users SET cash = :new_ammount WHERE id = :id", new_amount=new_amount, id=session["user_id"])
            
            # update history
            db.execute("INSERT INTO history (symbol, action, shares, price, id, date) VALUES(:symbol, :action, :shares, :price, :id, :date)", symbol=stock_info["symbol"], action="BOUGHT", shares=shares, price=usd(stock_info["price"]), id=session["user_id"], date=datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
            
            # check if user has shares of submitted symbol
            user_shares = db.execute("SELECT shares FROM portfolio WHERE id = :id AND symbol=:symbol", id=session["user_id"], symbol=stock_info["symbol"])
            
            
            # if not shares from this stock, insert info into portfolio table 
            if not user_shares:
                result = db.execute("INSERT INTO portfolio (id, name, symbol,shares, price,total) VALUES(:id, :name, :symbol, :shares, :price, :total)", id=session["user_id"], name=name, symbol=stock_info["symbol"], shares=shares, price=usd(stock_info["price"]), total=total_cost)
            
            else:
                total_shares = user_shares[0]["shares"] + shares
                db.execute("UPDATE portfolio SET shares=:shares WHERE id=:id AND symbol=:symbol", shares=total_shares, id=session["user_id"], symbol=stock_info["symbol"])
                
            # redirect to home page
            return redirect(url_for("index"))
            
    else:
        return render_template("buy.html")
        
        
@app.route("/history")
@login_required
def history():
    history = db.execute("SELECT * from history WHERE id=:id", id=session["user_id"])
    
    return render_template("history.html", history=history)

@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in."""

    # forget any user_id
    session.clear()

    # if user reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username")

        # ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password")

        # query database for username
        rows = db.execute("SELECT * FROM users WHERE username = :username", username=request.form.get("username"))

        # ensure username exists and password is correct
        if len(rows) != 1 or not pwd_context.verify(request.form.get("password"), rows[0]["hash"]):
            return apology("invalid username and/or password")

        # remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # redirect user to home page
        return redirect(url_for("index"))

    # else if user reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")

@app.route("/logout")
def logout():
    """Log user out."""

    # forget any user_id
    session.clear()

    # redirect user to login form
    return redirect(url_for("login"))

@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    
    if request.method == "POST":
        """Get stock quote."""
        result = lookup(request.form.get("symbol"))
        if not result:
            return apology("stock not valid")
            
        return stock(result)
    
    else:
        return render_template("quote.html")
        
@app.route("/stock", methods=["GET","POST"])
def stock(info):
    return render_template("stock.html", name=info['name'], price=usd(info['price']), symbol=info['symbol'])
    
    
    

@app.route("/register", methods=["GET", "POST"])
def register():
     # if user reached route via POST (as by submitting a form via POST)
    if request.method == "POST":
        
        # ensure user puts username
        if not request.form.get("username"):
            return apology("Missing username!")
         
        # ensure user puts password and password matches password confirmation   
        elif not request.form.get("password"):
            return apology("Missing password!")
        elif request.form.get("password") != request.form.get("confirmPassword"):
            return apology("Passwords must match")
        
        # store password in a hash
        hash = pwd_context.encrypt(request.form.get("password")) # --> or maybe just 'password'
        hash
        '$pbkdf2-sha256$7252$qKFNyMYTmgQDCFDS.jRJDQ$sms3/EWbs4/3k3aOoid5azwq3HPZKVpUUrAsCfjrN6M'
         
        # check if username already exists  
        result = db.execute("INSERT INTO users (username, hash) VALUES(:username, :hash)", username=request.form.get("username"), hash=hash)
        if not result:
            return apology("Username already exists")
        
        #return login()
        
        # query database for username
        rows = db.execute("SELECT * FROM users WHERE username = :username", username=request.form.get("username"))
         # remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # redirect user to home page
        return redirect(url_for("index"))
        
    
    else:
        return render_template("register.html")
    

@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock."""
    if request.method == "POST":
        
        
        symbol = request.form.get("symbol")
        s = request.form.get("quantity")
        for c in s:
            if c not in "0123456789":
                return apology("wrong input")
                
        sold_shares = int(request.form.get("quantity"))
        
        # ensure user provides symbol and quantity
        if not symbol or not sold_shares:
            return apology("must provide stock symbol and quantity")
            
        else:
        
            stock_info = lookup(symbol)
            
            # ensure user has provided stock
            row = db.execute("SELECT * FROM portfolio WHERE id=:id and symbol=:symbol", id=session["user_id"], symbol=symbol)
            if len(row) != 1:
               return apology("stock not found") 
               
            else:
                # check share amount
                shares = db.execute("SELECT shares FROM portfolio WHERE id=:id and symbol=:symbol", id=session["user_id"], symbol=symbol)
                
                # inform the user if share amount is less than amount to sell 
                if float(shares[0]["shares"]) < sold_shares:
                    return apology("you do not have that many shares, you only hava {} shares from {}".format(int(shares[0]["shares"]), symbol))
            
                else:
                    # calculate sold share total value
                    sold_price = stock_info["price"] * sold_shares  
        
                    # update portfolio (shares, total)
                    db.execute("UPDATE portfolio SET shares=shares - :sold_shares WHERE id=:id and symbol=:symbol", sold_shares=sold_shares, id=session["user_id"], symbol=symbol)
                    
                    #update user's cash
                    db.execute("UPDATE users SET cash=cash + :sold_price WHERE id=:id", sold_price=sold_price, id=session["user_id"])
                    
                # delete stock from portfolio if number of shares equals zero
                new_shares = db.execute("SELECT shares FROM portfolio where id=:id and symbol=:symbol", id=session["user_id"], symbol=symbol)
                if int(new_shares[0]["shares"]) == 0:
                    db.execute("DELETE FROM portfolio WHERE symbol=:symbol and id=:id", symbol=symbol, id=session["user_id"])
                    
                # update history
                db.execute("INSERT INTO history (symbol, action, shares, price, id, date) VALUES(:symbol, :action, :shares, :price, :id, :date)", symbol=stock_info["symbol"], action="SOLD", shares=sold_shares, price=usd(stock_info["price"]), id=session["user_id"], date=datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
                
                # redirect to home page
                return redirect(url_for("index"))
    else:
        return render_template("sell.html")
        
        
@app.route("/add", methods=["GET", "POST"])
def add():
    """add more cash to account"""
    
    if request.method == "POST":
        nums = '0123456789.'
        # make sure uers provide numbers and get rid of colons, if any
        s = request.form.get("amount")
        for c in s:
            if c not in nums:
                return apology("wrong input")
        
        deposit = float(s)
    
        # ensure user provides positive amount for deposit
        if not deposit or deposit <= 0:
            return apology("Must provide a positive amount for deposit")
     
        # else add cash to users
        else:
            db.execute("UPDATE users SET cash=cash + :deposit WHERE id=:id", deposit=deposit, id=session["user_id"])
    
        # updae history
            db.execute("INSERT INTO history (action, price, id, date) VALUES(:action, :price, :id, :date)", action="CASH DEPOSIT", price=usd(deposit), id=session["user_id"], date=datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
    
        # redirect user to homepage    
        return redirect(url_for("index"))
    
    else:
        return render_template("add.html")
    
