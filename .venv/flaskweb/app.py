import sys
from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta
from sqlalchemy import func
import os

# 提高递归深度限制
sys.setrecursionlimit(10000)

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-here'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///study_logs.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)


# 科目模型
class Subject(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)  # 科目名称
    description = db.Column(db.Text)  # 科目描述
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    # 关联的学习记录 - 级联删除
    logs = db.relationship('StudyLog', backref='subject', lazy=True, cascade="all, delete-orphan")

    # 计算该科目的总学习时长
    @property
    def total_duration(self):
        return round(sum(log.duration for log in self.logs), 1)

    # 计算该科目的学习次数
    @property
    def total_sessions(self):
        return len(self.logs)

    # 计算该科目的最近学习时间
    @property
    def last_studied(self):
        if self.logs:
            completed_logs = [log for log in self.logs if log.end_time]
            return max(log.end_time for log in completed_logs) if completed_logs else None
        return None


# 学习记录模型
class StudyLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    subject_id = db.Column(db.Integer, db.ForeignKey('subject.id'), nullable=False)  # 关联科目
    start_time = db.Column(db.DateTime, nullable=False)  # 开始时间
    end_time = db.Column(db.DateTime)  # 结束时间（null表示正在学习）
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # 计算学习时长（小时）
    @property
    def duration(self):
        if not self.end_time:
            return 0
        delta = self.end_time - self.start_time
        return round(delta.total_seconds() / 3600, 1)

    # 判断是否正在学习中
    @property
    def is_active(self):
        return self.end_time is None


# 初始化数据库
with app.app_context():
    db.create_all()


# 辅助函数：计算连续打卡天数
def get_streak_days():
    try:
        today = datetime.now().date()
        yesterday = today - timedelta(days=1)

        # 检查今天是否有记录
        has_today = StudyLog.query.filter(
            db.func.date(StudyLog.start_time) == today,
            StudyLog.end_time != None  # 只算已完成的
        ).first() is not None

        # 基础连续天数
        streak = 1 if has_today else 0
        max_check = 365  # 最多检查365天
        checked = 0

        # 如果今天有记录，检查之前的日期
        if has_today:
            current_date = yesterday
            while checked < max_check:
                has_record = StudyLog.query.filter(
                    db.func.date(StudyLog.start_time) == current_date,
                    StudyLog.end_time != None
                ).first() is not None

                if has_record:
                    streak += 1
                    current_date -= timedelta(days=1)
                    checked += 1
                else:
                    break

        return streak
    except Exception as e:
        print(f"计算连续打卡错误：{e}")
        return 0


# 辅助函数：计算本月学习总时长
def get_monthly_duration():
    try:
        today = datetime.now()
        start_of_month = datetime(today.year, today.month, 1)
        logs = StudyLog.query.filter(
            StudyLog.start_time >= start_of_month,
            StudyLog.end_time != None
        ).all()
        return round(sum(log.duration for log in logs), 1)
    except Exception as e:
        print(f"计算月时长错误：{e}")
        return 0


# 辅助函数：计算本周学习时长
def get_weekly_duration():
    try:
        today = datetime.now()
        start_of_week = today - timedelta(days=today.weekday())  # 周一
        start_of_week = datetime(start_of_week.year, start_of_week.month, start_of_week.day)

        logs = StudyLog.query.filter(
            StudyLog.start_time >= start_of_week,
            StudyLog.end_time != None
        ).all()

        return round(sum(log.duration for log in logs), 1)
    except Exception as e:
        print(f"计算周时长错误：{e}")
        return 0


# 首页路由
@app.route('/')
def index():
    # 初始化所有模板中需要的变量
    subjects = []
    active_logs = []
    recent_logs = []
    streak_days = 0
    monthly_duration = 0
    weekly_duration = 0
    weekly_goal = 28
    monthly_goal = 120
    weekly_percentage = 0
    monthly_percentage = 0
    efficiency_score = 85

    try:
        # 获取所有科目
        subjects = Subject.query.all()

        # 获取进行中的学习
        active_logs = StudyLog.query.filter(StudyLog.end_time == None).all()

        # 计算统计数据
        streak_days = get_streak_days()
        monthly_duration = get_monthly_duration()
        weekly_duration = get_weekly_duration()

        # 计算百分比（添加除以零保护）
        weekly_percentage = min(100, (weekly_duration / weekly_goal) * 100) if weekly_goal > 0 else 0
        monthly_percentage = min(100, (monthly_duration / monthly_goal) * 100) if monthly_goal > 0 else 0

        # 获取最近的学习记录
        recent_logs = StudyLog.query.filter(StudyLog.end_time != None).order_by(StudyLog.end_time.desc()).limit(5).all()

    except Exception as e:
        flash(f"加载首页出错：{str(e)}", "danger")

    # 确保传递所有模板需要的变量
    return render_template('index.html',
                           subjects=subjects,
                           active_logs=active_logs,
                           recent_logs=recent_logs,
                           streak_days=streak_days,
                           monthly_duration=monthly_duration,
                           monthly_goal=monthly_goal,
                           monthly_percentage=monthly_percentage,
                           weekly_duration=weekly_duration,
                           weekly_goal=weekly_goal,
                           weekly_percentage=weekly_percentage,
                           efficiency_score=efficiency_score,
                           now=datetime.now())


# 科目管理路由
@app.route('/subjects')
def subjects():
    subjects = Subject.query.all()
    return render_template('subjects.html', subjects=subjects, now=datetime.now())


# 添加科目
@app.route('/subjects/add', methods=['GET', 'POST'])
def add_subject():
    if request.method == 'POST':
        try:
            name = request.form['name'].strip()
            description = request.form['description'].strip()

            # 验证
            if not name:
                flash('科目名称不能为空', 'danger')
                return render_template('add_subject.html', now=datetime.now())

            # 检查是否已存在
            existing = Subject.query.filter_by(name=name).first()
            if existing:
                flash('该科目已存在', 'danger')
                return render_template('add_subject.html', now=datetime.now())

            # 创建新科目
            new_subject = Subject(name=name, description=description)
            db.session.add(new_subject)
            db.session.commit()

            flash(f'科目 "{name}" 添加成功', 'success')
            return redirect(url_for('subjects'))

        except Exception as e:
            db.session.rollback()
            flash(f'添加科目出错：{str(e)}', 'danger')
            return render_template('add_subject.html', now=datetime.now())

    return render_template('add_subject.html', now=datetime.now())


# 科目详情页（完善版）
@app.route('/subjects/<int:id>')
def subject_detail(id):
    try:
        # 尝试查询科目，不存在则返回404
        subject = Subject.query.get_or_404(id)

        # 获取该科目的所有学习记录
        logs = StudyLog.query.filter_by(subject_id=id).order_by(StudyLog.start_time.desc()).all()

        # 计算本月该科目的学习时长
        today = datetime.now()
        start_of_month = datetime(today.year, today.month, 1)
        monthly_logs = StudyLog.query.filter(
            StudyLog.subject_id == id,
            StudyLog.start_time >= start_of_month,
            StudyLog.end_time != None
        ).all()
        monthly_duration = round(sum(log.duration for log in monthly_logs), 1)

        # 计算本周该科目的学习时长
        start_of_week = today - timedelta(days=today.weekday())
        weekly_logs = StudyLog.query.filter(
            StudyLog.subject_id == id,
            StudyLog.start_time >= start_of_week,
            StudyLog.end_time != None
        ).all()
        weekly_duration = round(sum(log.duration for log in weekly_logs), 1)

        # 获取URL中的目标时长参数（用于计时器）
        target_hours = request.args.get('hours', 0, type=int)
        target_minutes = request.args.get('minutes', 0, type=int)

        return render_template('subject_detail.html',
                            subject=subject,
                            logs=logs,
                            monthly_duration=monthly_duration,
                            weekly_duration=weekly_duration,
                            target_hours=target_hours,
                            target_minutes=target_minutes,
                            now=datetime.now())
    except Exception as e:
        flash(f'加载科目详情出错：{str(e)}', 'danger')
        # 出错时跳转到科目列表
        return redirect(url_for('subjects'))



# 开始学习
@app.route('/subjects/<int:subject_id>/start', methods=['GET'])
def start_checkin(subject_id):
    try:
        # 获取目标时长参数
        hours = request.args.get('hours', 0, type=int)
        minutes = request.args.get('minutes', 0, type=int)

        # 验证参数有效性
        if hours < 0 or hours > 24 or minutes < 0 or minutes > 59 or (hours == 0 and minutes == 0):
            flash('请设置有效的学习时长（至少1分钟）', 'danger')
            return redirect(url_for('subject_detail', id=subject_id))

        # 检查是否已有活跃记录
        active_log = StudyLog.query.filter_by(
            subject_id=subject_id,
            end_time=None
        ).first()

        if active_log:
            flash('该科目已有进行中的学习记录', 'warning')
            return redirect(url_for('subject_detail', id=subject_id))

        # 创建新的学习记录
        new_log = StudyLog(
            subject_id=subject_id,
            start_time=datetime.now()
        )
        db.session.add(new_log)
        db.session.commit()

        # 携带目标时长参数跳转回详情页
        return redirect(url_for('subject_detail',
                                id=subject_id,
                                hours=hours,
                                minutes=minutes))

    except Exception as e:
        db.session.rollback()
        flash(f'开始学习出错：{str(e)}', 'danger')
        return redirect(url_for('subject_detail', id=subject_id))


# 结束学习
@app.route('/logs/<int:log_id>/end', methods=['GET'])
def end_checkin(log_id):
    try:
        log = StudyLog.query.get_or_404(log_id)
        if log.end_time:
            flash('该学习记录已结束', 'warning')
            return redirect(url_for('subject_detail', id=log.subject_id))

        log.end_time = datetime.now()
        db.session.commit()
        flash('学习记录已更新', 'success')
        return redirect(url_for('subject_detail', id=log.subject_id))

    except Exception as e:
        db.session.rollback()
        flash(f'结束学习出错：{str(e)}', 'danger')
        return redirect(url_for('index'))


# 编辑科目
@app.route('/subjects/edit/<int:id>', methods=['GET', 'POST'])
def edit_subject(id):
    subject = Subject.query.get_or_404(id)

    if request.method == 'POST':
        try:
            name = request.form['name'].strip()
            description = request.form['description'].strip()

            if not name:
                flash('科目名称不能为空', 'danger')
                return render_template('edit_subject.html', subject=subject, now=datetime.now())

            # 检查名称是否已被其他科目使用
            existing = Subject.query.filter_by(name=name).first()
            if existing and existing.id != id:
                flash('该科目名称已被使用', 'danger')
                return render_template('edit_subject.html', subject=subject, now=datetime.now())

            subject.name = name
            subject.description = description
            db.session.commit()

            flash('科目已更新', 'success')
            return redirect(url_for('subject_detail', id=id))

        except Exception as e:
            db.session.rollback()
            flash(f'编辑科目出错：{str(e)}', 'danger')
            return render_template('edit_subject.html', subject=subject, now=datetime.now())

    return render_template('edit_subject.html', subject=subject, now=datetime.now())


# 删除学习记录
@app.route('/logs/<int:log_id>/delete', methods=['GET'])
def delete_log(log_id):
    try:
        log = StudyLog.query.get_or_404(log_id)
        subject_id = log.subject_id
        db.session.delete(log)
        db.session.commit()
        flash('学习记录已删除', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'删除记录出错：{str(e)}', 'danger')
    return redirect(url_for('subject_detail', id=subject_id))


# 删除科目
@app.route('/subjects/delete/<int:id>', methods=['POST'])
def delete_subject(id):
    try:
        subject = Subject.query.get_or_404(id)

        # 检查是否有活跃的学习记录
        active_logs = StudyLog.query.filter_by(subject_id=id, end_time=None).first()
        if active_logs:
            flash('无法删除有进行中学习记录的科目', 'danger')
            return redirect(url_for('subjects'))

        db.session.delete(subject)
        db.session.commit()
        flash(f'科目 "{subject.name}" 已成功删除', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'删除科目出错：{str(e)}', 'danger')
    return redirect(url_for('subjects'))


if __name__ == '__main__':
    app.run(debug=True)
