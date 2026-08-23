from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
import json
import os
from functools import wraps

app = Flask(__name__)
app.config['SECRET_KEY'] = os.urandom(24).hex()
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///quindecillion.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=30)

db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# ==================== DATABASE MODELS ====================
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    business_name = db.Column(db.String(200))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login = db.Column(db.DateTime)
    
    # Relationships
    business_plans = db.relationship('BusinessPlan', backref='owner', lazy=True)
    avatars = db.relationship('Avatar', backref='creator', lazy=True)
    delivery_checklists = db.relationship('DeliveryChecklist', backref='owner', lazy=True)
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class BusinessPlan(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    vision_3year = db.Column(db.JSON)
    goals_1year = db.Column(db.JSON)
    strategy_90day = db.Column(db.JSON)
    this_week_actions = db.Column(db.JSON)
    six_ps = db.Column(db.JSON)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    progress = db.Column(db.Integer, default=0)

class Avatar(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    name = db.Column(db.String(100))
    demographics = db.Column(db.JSON)
    psychographics = db.Column(db.JSON)
    pains_frustrations = db.Column(db.JSON)
    goals_desires = db.Column(db.JSON)
    fears_implications = db.Column(db.JSON)
    dreams_aspirations = db.Column(db.JSON)
    marketplace_sophistication = db.Column(db.String(50))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class DeliveryChecklist(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    program_name = db.Column(db.String(200))
    transformation_from = db.Column(db.String(300))
    transformation_to = db.Column(db.String(300))
    steps = db.Column(db.JSON)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# ==================== DECORATORS ====================
def api_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            return jsonify({'error': 'Authentication required'}), 401
        return f(*args, **kwargs)
    return decorated_function

# ==================== ROUTES ====================
@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return render_template('landing.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        data = request.get_json() if request.is_json else request.form
        email = data.get('email')
        password = data.get('password')
        user = User.query.filter_by(email=email).first()
        
        if user and user.check_password(password):
            user.last_login = datetime.utcnow()
            db.session.commit()
            login_user(user, remember=True)
            if request.is_json:
                return jsonify({'success': True, 'redirect': url_for('dashboard')})
            return redirect(url_for('dashboard'))
        
        if request.is_json:
            return jsonify({'success': False, 'error': 'Invalid credentials'}), 401
        return render_template('login.html', error='Invalid credentials')
    
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        data = request.get_json() if request.is_json else request.form
        email = data.get('email')
        password = data.get('password')
        name = data.get('name')
        business_name = data.get('business_name', '')
        
        if User.query.filter_by(email=email).first():
            if request.is_json:
                return jsonify({'success': False, 'error': 'Email already registered'}), 400
            return render_template('register.html', error='Email already registered')
        
        user = User(email=email, name=name, business_name=business_name)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        
        login_user(user)
        if request.is_json:
            return jsonify({'success': True, 'redirect': url_for('dashboard')})
        return redirect(url_for('dashboard'))
    
    return render_template('register.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

@app.route('/dashboard')
@login_required
def dashboard():
    stats = {
        'total_plans': BusinessPlan.query.filter_by(user_id=current_user.id).count(),
        'total_avatars': Avatar.query.filter_by(user_id=current_user.id).count(),
        'total_checklists': DeliveryChecklist.query.filter_by(user_id=current_user.id).count(),
        'recent_plans': BusinessPlan.query.filter_by(user_id=current_user.id).order_by(
            BusinessPlan.updated_at.desc()
        ).limit(5).all()
    }
    return render_template('dashboard.html', stats=stats)

# ==================== BUSINESS PLAN API ====================
@app.route('/api/business-plans', methods=['GET'])
@api_required
def get_business_plans():
    plans = BusinessPlan.query.filter_by(user_id=current_user.id).all()
    return jsonify([{
        'id': p.id,
        'title': p.title,
        'progress': p.progress,
        'updated_at': p.updated_at.isoformat(),
        'created_at': p.created_at.isoformat()
    } for p in plans])

@app.route('/api/business-plans', methods=['POST'])
@api_required
def create_business_plan():
    data = request.get_json()
    plan = BusinessPlan(
        user_id=current_user.id,
        title=data.get('title', 'New Business Plan'),
        vision_3year=data.get('vision_3year', {}),
        goals_1year=data.get('goals_1year', {}),
        strategy_90day=data.get('strategy_90day', {}),
        this_week_actions=data.get('this_week_actions', {}),
        six_ps=data.get('six_ps', {})
    )
    db.session.add(plan)
    db.session.commit()
    return jsonify({'success': True, 'id': plan.id}), 201

@app.route('/api/business-plans/<int:plan_id>', methods=['GET'])
@api_required
def get_business_plan(plan_id):
    plan = BusinessPlan.query.filter_by(id=plan_id, user_id=current_user.id).first_or_404()
    return jsonify({
        'id': plan.id,
        'title': plan.title,
        'vision_3year': plan.vision_3year,
        'goals_1year': plan.goals_1year,
        'strategy_90day': plan.strategy_90day,
        'this_week_actions': plan.this_week_actions,
        'six_ps': plan.six_ps,
        'progress': plan.progress,
        'updated_at': plan.updated_at.isoformat()
    })

@app.route('/api/business-plans/<int:plan_id>', methods=['PUT'])
@api_required
def update_business_plan(plan_id):
    plan = BusinessPlan.query.filter_by(id=plan_id, user_id=current_user.id).first_or_404()
    data = request.get_json()
    
    for key in ['title', 'vision_3year', 'goals_1year', 'strategy_90day', 
                'this_week_actions', 'six_ps', 'progress']:
        if key in data:
            setattr(plan, key, data[key])
    
    db.session.commit()
    return jsonify({'success': True})

@app.route('/api/business-plans/<int:plan_id>', methods=['DELETE'])
@api_required
def delete_business_plan(plan_id):
    plan = BusinessPlan.query.filter_by(id=plan_id, user_id=current_user.id).first_or_404()
    db.session.delete(plan)
    db.session.commit()
    return jsonify({'success': True})

# ==================== AVATAR API ====================
@app.route('/api/avatars', methods=['GET'])
@api_required
def get_avatars():
    avatars = Avatar.query.filter_by(user_id=current_user.id).all()
    return jsonify([{
        'id': a.id,
        'name': a.name,
        'marketplace_sophistication': a.marketplace_sophistication,
        'created_at': a.created_at.isoformat()
    } for a in avatars])

@app.route('/api/avatars', methods=['POST'])
@api_required
def create_avatar():
    data = request.get_json()
    avatar = Avatar(
        user_id=current_user.id,
        name=data.get('name', 'New Avatar'),
        demographics=data.get('demographics', {}),
        psychographics=data.get('psychographics', {}),
        pains_frustrations=data.get('pains_frustrations', []),
        goals_desires=data.get('goals_desires', []),
        fears_implications=data.get('fears_implications', []),
        dreams_aspirations=data.get('dreams_aspirations', []),
        marketplace_sophistication=data.get('marketplace_sophistication', 'unaware')
    )
    db.session.add(avatar)
    db.session.commit()
    return jsonify({'success': True, 'id': avatar.id}), 201

# ==================== DELIVERY CHECKLIST API ====================
@app.route('/api/delivery-checklists', methods=['GET'])
@api_required
def get_delivery_checklists():
    checklists = DeliveryChecklist.query.filter_by(user_id=current_user.id).all()
    return jsonify([{
        'id': c.id,
        'program_name': c.program_name,
        'transformation_from': c.transformation_from,
        'transformation_to': c.transformation_to,
        'created_at': c.created_at.isoformat()
    } for c in checklists])

@app.route('/api/delivery-checklists', methods=['POST'])
@api_required
def create_delivery_checklist():
    data = request.get_json()
    checklist = DeliveryChecklist(
        user_id=current_user.id,
        program_name=data.get('program_name'),
        transformation_from=data.get('transformation_from'),
        transformation_to=data.get('transformation_to'),
        steps=data.get('steps', [])
    )
    db.session.add(checklist)
    db.session.commit()
    return jsonify({'success': True, 'id': checklist.id}), 201

# ==================== ANALYTICS API ====================
@app.route('/api/analytics/summary', methods=['GET'])
@api_required
def get_analytics_summary():
    plans_count = BusinessPlan.query.filter_by(user_id=current_user.id).count()
    avatars_count = Avatar.query.filter_by(user_id=current_user.id).count()
    checklists_count = DeliveryChecklist.query.filter_by(user_id=current_user.id).count()
    
    return jsonify({
        'total_plans': plans_count,
        'total_avatars': avatars_count,
        'total_checklists': checklists_count,
        'completion_rate': 85,  # Calculate based on actual data
        'recent_activity': {
            'last_7_days': 3,
            'last_30_days': 12
        }
    })

# ==================== ERROR HANDLERS ====================
@app.errorhandler(404)
def not_found_error(error):
    if request.is_json:
        return jsonify({'error': 'Not found'}), 404
    return render_template('404.html'), 404

@app.errorhandler(500)
def internal_error(error):
    db.session.rollback()
    if request.is_json:
        return jsonify({'error': 'Internal server error'}), 500
    return render_template('500.html'), 500

# Initialize database
with app.app_context():
    db.create_all()

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
