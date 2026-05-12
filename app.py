from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.config['SECRET_KEY'] = 'change-me'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///inventory.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default='Viewer')

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Category(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)

class Supplier(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    contact = db.Column(db.String(120))
    address = db.Column(db.String(200))

class Supply(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    item_id = db.Column(db.String(50), unique=True, nullable=False)
    item_name = db.Column(db.String(120), nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey('category.id'))
    description = db.Column(db.Text)
    quantity = db.Column(db.Integer, default=0)
    unit_price = db.Column(db.Float, default=0.0)
    supplier_id = db.Column(db.Integer, db.ForeignKey('supplier.id'))
    date_purchased = db.Column(db.Date)
    expiration_date = db.Column(db.Date)
    storage_location = db.Column(db.String(120))
    status = db.Column(db.String(50), default='Available')
    date_added = db.Column(db.DateTime, default=datetime.utcnow)

    category = db.relationship('Category')
    supplier = db.relationship('Supplier')

class Transaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    supply_id = db.Column(db.Integer, db.ForeignKey('supply.id'))
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    tx_type = db.Column(db.String(20), nullable=False)  # IN/OUT
    quantity = db.Column(db.Integer, nullable=False)
    department = db.Column(db.String(120))
    receiver = db.Column(db.String(120))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    supply = db.relationship('Supply')
    user = db.relationship('User')

class Report(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    report_type = db.Column(db.String(20), nullable=False)  # Daily/Weekly/Monthly/Annual
    format = db.Column(db.String(10), nullable=False, default='CSV')
    generated_by = db.Column(db.Integer, db.ForeignKey('user.id'))
    generated_at = db.Column(db.DateTime, default=datetime.utcnow)
    notes = db.Column(db.String(255))

    user = db.relationship('User')

class AuditLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    action = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    user = db.relationship('User')

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

def role_required(*roles):
    def wrapper(fn):
        from functools import wraps
        @wraps(fn)
        def inner(*args, **kwargs):
            if current_user.role not in roles:
                flash('Access denied.', 'danger')
                return redirect(url_for('dashboard'))
            return fn(*args, **kwargs)
        return inner
    return wrapper

def log_action(action):
    if current_user.is_authenticated:
        db.session.add(AuditLog(user_id=current_user.id, action=action))
        db.session.commit()

@app.route('/init')
def init_db():
    db.create_all()
    if not User.query.filter_by(username='admin').first():
        admin = User(username='admin', role='Admin')
        admin.set_password('admin123')
        db.session.add(admin)
        for name in ['Office Supplies', 'Cleaning Materials', 'Electronics', 'Medical Supplies', 'School Materials']:
            db.session.add(Category(name=name))
        db.session.commit()
    return 'Initialized. Default admin: admin/admin123'

@app.route('/', methods=['GET'])
def index():
    return redirect(url_for('dashboard' if current_user.is_authenticated else 'login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = User.query.filter_by(username=request.form['username']).first()
        if user and user.check_password(request.form['password']):
            login_user(user)
            log_action('Logged in')
            return redirect(url_for('dashboard'))
        flash('Invalid credentials.', 'danger')
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
@login_required
@role_required('Admin')
def register():
    if request.method == 'POST':
        user = User(username=request.form['username'], role=request.form['role'])
        user.set_password(request.form['password'])
        db.session.add(user)
        db.session.commit()
        log_action(f'Registered user: {user.username}')
        flash('User created.', 'success')
        return redirect(url_for('register'))
    return render_template('register.html')

@app.route('/logout')
@login_required
def logout():
    log_action('Logged out')
    logout_user()
    return redirect(url_for('login'))

@app.route('/dashboard')
@login_required
def dashboard():
    supplies = Supply.query.all()
    total = len(supplies)
    available = sum(s.quantity for s in supplies)
    low_stock = [s for s in supplies if s.quantity < 10 and s.quantity > 0]
    out_of_stock = [s for s in supplies if s.quantity == 0]
    recent = Transaction.query.order_by(Transaction.created_at.desc()).limit(5).all()
    reports_count = Report.query.count()
    return render_template('dashboard.html', total=total, available=available, low_stock=low_stock, out_of_stock=out_of_stock, recent=recent, reports_count=reports_count)


@app.route('/reports', methods=['GET', 'POST'])
@login_required
def reports():
    if request.method == 'POST':
        report = Report(
            report_type=request.form.get('report_type', 'Monthly'),
            format=request.form.get('format', 'CSV'),
            generated_by=current_user.id,
            notes=request.form.get('notes', '')
        )
        db.session.add(report)
        db.session.commit()
        log_action(f"Generated {report.report_type} report ({report.format})")
        flash('Report entry created.', 'success')
        return redirect(url_for('reports'))

    all_reports = Report.query.order_by(Report.generated_at.desc()).all()
    return render_template('reports.html', reports=all_reports)

@app.route('/supplies', methods=['GET', 'POST'])
@login_required
def supplies():
    if request.method == 'POST':
        s = Supply(
            item_id=request.form['item_id'], item_name=request.form['item_name'],
            category_id=request.form.get('category_id') or None,
            description=request.form.get('description'), quantity=int(request.form.get('quantity', 0)),
            unit_price=float(request.form.get('unit_price', 0)),
            supplier_id=request.form.get('supplier_id') or None,
            storage_location=request.form.get('storage_location'), status=request.form.get('status', 'Available')
        )
        db.session.add(s)
        db.session.commit()
        log_action(f'Added supply: {s.item_name}')
        flash('Supply added.', 'success')
        return redirect(url_for('supplies'))

    q = request.args.get('q', '')
    category = request.args.get('category', '')
    query = Supply.query
    if q:
        query = query.filter(Supply.item_name.ilike(f'%{q}%'))
    if category:
        query = query.join(Category).filter(Category.name == category)
    return render_template('supplies.html', supplies=query.order_by(Supply.date_added.desc()).all(), categories=Category.query.all(), suppliers=Supplier.query.all())

if __name__ == '__main__':
    app.run(debug=True)
