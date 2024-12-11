
from flask import Flask, render_template, request, redirect, url_for, flash, send_file
from flask_sqlalchemy import SQLAlchemy
import random
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
import os  
from PyPDF2 import PdfMerger  # Import PdfMerger from PyPDF2
# excel file generate
import openpyxl
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter
from flask import send_file
import os
import io


app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///timetable.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = 'your_secret_key_here'  # Required for flash messages
db = SQLAlchemy(app)

# Database Models
class Classroom(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    capacity = db.Column(db.Integer, nullable=False)

class Batch(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)

class Course(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    credits = db.Column(db.Integer, nullable=False)
    is_lab = db.Column(db.Boolean, default=False)
    priority = db.Column(db.Boolean, default=False)  # Make sure this line is present

class Professor(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)

class Schedule(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    batch_id = db.Column(db.Integer, db.ForeignKey('batch.id'), nullable=False)
    course_id = db.Column(db.Integer, db.ForeignKey('course.id'), nullable=False)
    professor_id = db.Column(db.Integer, db.ForeignKey('professor.id'), nullable=False)
    day = db.Column(db.Integer, nullable=False)  # 0-4 for Monday-Friday
    slot = db.Column(db.Integer, nullable=False)  # 0-8 for time slots
    classroom_id = db.Column(db.Integer, db.ForeignKey('classroom.id'), nullable=True)

# roomallotment 
def find_available_classroom(day, slot):
    all_classrooms = Classroom.query.all()
    for classroom in all_classrooms:
        existing_schedule = Schedule.query.filter_by(
            classroom_id=classroom.id, day=day, slot=slot
        ).first()
        if not existing_schedule:
            return classroom
    return None

# Helper function to check if a slot is available
def is_slot_available(batch_id, professor_id, day, slot, is_lab=False):
    if is_lab:
        # Check for three consecutive slots for a lab
        if slot > 6 or slot == 2 or slot == 4 or slot ==3 :  # Can't start a lab if the starting slot is beyond 6 (not enough space for 3 slots)
            return False
        for offset in range(3):
            existing_schedule = Schedule.query.filter_by(
                batch_id=batch_id, day=day, slot=slot + offset
            ).first()
            professor_schedule = Schedule.query.filter_by(
                professor_id=professor_id, day=day, slot=slot + offset
            ).first()
            if existing_schedule or professor_schedule:
                return False
        return True
    else:
        # Check single slot availability for non-lab courses
        existing_schedule = Schedule.query.filter_by(
            batch_id=batch_id, day=day, slot=slot
        ).first()
        professor_schedule = Schedule.query.filter_by(
            professor_id=professor_id, day=day, slot=slot
        ).first()
        return not (existing_schedule or professor_schedule)



# excel code

def merge_excel_files():
    # Create a new workbook to store the merged result
    merged_wb = openpyxl.Workbook()
    merged_ws = merged_wb.active
    merged_ws.title = "Merged Timetables"
    
    batches = Batch.query.all()  # Get all batches from the database
    row_offset = 0  # This will be used to track where to place each batch's data
    
    # Define time slots
    time_slots = ["08:00 AM - 09:00 AM", "09:00 AM - 10:00 AM", "10:00 AM - 11:00 AM",
                  "11:00 AM - 12:00 PM", "12:00 PM - 01:00 PM", "01:00 PM - 02:00 PM",
                  "02:00 PM - 03:00 PM", "03:00 PM - 04:00 PM", "04:00 PM - 05:00 PM"]
    
    for batch in batches:
        excel_path = generate_excel(batch.id)  # Generate each batch's Excel file
        wb = openpyxl.load_workbook(excel_path)  # Load the batch's Excel file
        ws = wb.active  # Access the active sheet
        
        # Create a new sheet in the merged workbook for this batch
        batch_sheet = merged_wb.create_sheet(title=f"Batch {batch.id}")
        
        # Copy header time slots
        for col_index, time_slot in enumerate(time_slots, start=1):
            col_letter = get_column_letter(col_index)
            batch_sheet[f"{col_letter}1"] = time_slot
            batch_sheet[f"{col_letter}1"].font = Font(size=12, bold=True)
        
        # Copy content from the batch's Excel file to the merged workbook
        for row in ws.iter_rows(min_row=1, max_row=ws.max_row, min_col=1, max_col=ws.max_column):
            for col_index, cell in enumerate(row, start=1):
                batch_sheet.cell(row=row_offset + cell.row, column=col_index, value=cell.value)
        
        row_offset += ws.max_row + 2  # Add some space between batches (extra row to separate)
    
    # Save the merged workbook to a file
    merged_excel_path = r"D:\New folder (2)\timetables\merged_batches.xlsx"
    merged_wb.save(merged_excel_path)  # Save the merged Excel workbook
    
    return merged_excel_path  # Return the path of the merged Excel file


def generate_excel(batch_id):
    batch = Batch.query.get(batch_id)
    schedules = Schedule.query.filter_by(batch_id=batch_id).all()

    # Time slots from 8 AM to 6 PM (10 slots)
    time_slots = [
        "08:00 AM - 09:00 AM", "09:00 AM - 10:00 AM", "10:00 AM - 11:00 AM",
        "11:00 AM - 12:00 PM", "12:00 PM - 01:00 PM", "01:00 PM - 02:00 PM",
        "02:00 PM - 03:00 PM", "03:00 PM - 04:00 PM", "04:00 PM - 05:00 PM", "05:00 PM - 06:00 PM"
    ]
    
    # Initialize the timetable with empty values ("-")
    timetable = [["-" for _ in range(10)] for _ in range(5)]  # 5 days, 10 time slots per day
    
    # Fill in the timetable based on schedules
    for schedule in schedules:
        course = Course.query.get(schedule.course_id)
        professor = Professor.query.get(schedule.professor_id)
        classroom= Classroom.query.get(schedule.classroom_id)
        timetable[schedule.day][schedule.slot] = f"{course.name}({professor.name}), Room: {classroom.name}"
        

    # Create a new Excel workbook and sheet
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = f"Batch {batch_id}"

    # Set the title row
    days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
    
    # Set header row
    ws['A1'] = f"Timetable for Batch: {batch.name}"
    ws['A1'].font = Font(size=14, bold=True)
    ws.merge_cells('A1:K1')  # Merge columns to fit time slots

    # Adding day and time slot headers
    ws['A2'] = "Day"
    for col_index, time_slot in enumerate(time_slots, start=2):
        col_letter = get_column_letter(col_index)
        ws[f'{col_letter}2'] = time_slot

    # Filling in the timetable data
    for day_index, day_name in enumerate(days):
        ws[f"A{day_index + 3}"] = day_name
        for slot_index, slot_content in enumerate(timetable[day_index]):
            col_letter = get_column_letter(slot_index + 2)
            ws[f"{col_letter}{day_index + 3}"] = slot_content

    # Save the Excel file to a path
    excel_path = f"D:/New folder (2)/timetables/batch_{batch_id}.xlsx"
    wb.save(excel_path)

    return excel_path

# excel file end

# Routes
@app.route('/')
def index():
    batches = Batch.query.all()
    return render_template('index.html', batches=batches)

@app.route('/create_batch', methods=['GET', 'POST'])
def create_batch():
    if request.method == 'POST':
        batch_name = request.form['name']
        new_batch = Batch(name=batch_name)
        db.session.add(new_batch)
        try:
            db.session.commit()
            flash('Batch created successfully', 'success')
        except:
            db.session.rollback()
            flash('Error creating batch', 'error')
        return redirect(url_for('index'))
    return render_template('create_batch.html')
# comment here caution

    # excel route

@app.route('/download_timetable/<int:batch_id>')
def download_timetable(batch_id):
    print(batch_id)
    excel_path = generate_excel(batch_id)  # Generate and save the Excel file

    # Ensure the Excel file exists before sending it
    if os.path.exists(excel_path):
        return send_file(excel_path, as_attachment=True)
    else:
        return "File not found", 404

@app.route('/download_all_batches')
def download_all_batches():
    # Merge all batches' Excel files into one
    merged_excel_path = merge_excel_files()  # This function merges all batch Excel files
    # Ensure the merged Excel file exists before sending it
    if os.path.exists(merged_excel_path):
        return send_file(merged_excel_path, as_attachment=True)
    else:
        return "File not found", 404
    
# excel route end

# classroom route
@app.route('/classrooms', methods=['GET', 'POST'])
def manage_classrooms():
    if request.method == 'POST':
        classroom_name = request.form['name']
        capacity = int(request.form['capacity'])
        new_classroom = Classroom(name=classroom_name, capacity=capacity)
        db.session.add(new_classroom)
        try:
            db.session.commit()
            flash('Classroom added successfully', 'success')
        except:
            db.session.rollback()
            flash('Error adding classroom', 'error')
        return redirect(url_for('manage_classrooms'))
    classrooms = Classroom.query.all()
    return render_template('classrooms.html', classrooms=classrooms)
# classroom route end

@app.route('/batch/<int:batch_id>', methods=['GET', 'POST'])
def manage_batch(batch_id):
    batch = Batch.query.get_or_404(batch_id)
    if request.method == 'POST':
        course_name = request.form['course_name']
        credits = int(request.form['credits'])
        is_lab = 'is_lab' in request.form
        priority = 'priority' in request.form
        priority_type = request.form.get('priority_type')  # Get the priority type

        professor_name = request.form['professor_name']
        course = Course.query.filter_by(name=course_name).first()
        if not course:
            course = Course(name=course_name, credits=credits, is_lab=is_lab, priority=priority)
            db.session.add(course)

        professor = Professor.query.filter_by(name=professor_name).first()
        if not professor:
            professor = Professor(name=professor_name)
            db.session.add(professor)

        try:
            db.session.commit()
        except:
            db.session.rollback()
            flash('Error adding course or professor', 'error')
            return redirect(url_for('manage_batch', batch_id=batch_id))

        # Schedule the course based on priority type
        available_slots = []
        if is_lab:
            for day in range(5):
                for slot in range(7):  # Only check up to slot 6 for labs
                    if is_slot_available(batch.id, professor.id, day, slot, is_lab=True) and slot!=4:
                        available_slots.append((day, slot))
                        break
        elif priority:
            if priority_type == "2-hour consecutive":
                for day in range(5):
                    for slot in range(8):  # Check up to slot 7 for consecutive slots
                        if slot != 3 and slot !=4:
                            if is_slot_available(batch.id, professor.id, day, slot) and is_slot_available(batch.id, professor.id, day, slot + 1):
                                available_slots.append((day, slot))
                                break
            elif priority_type == "2-1-1":
                for day in range(5):
                    for slot in range(8):  # Check up to slot 7 for consecutive slots
                        if slot != 3 and slot !=4:
                            if is_slot_available(batch.id, professor.id, day, slot) and is_slot_available(batch.id, professor.id, day, slot + 1) and slot!=4:
                                available_slots.append((day, slot))
                                break
                credits-=2
                for day in range(5):
                    for slot in range(9):  # Check all slots for 2-1-1 hours pattern
                        if is_slot_available(batch.id, professor.id, day, slot) and slot!=4 and credits>0:
                            available_slots.append((day, slot))
                            break
                credits-=1
                for day in range(5):
                    for slot in range(9):  # Check all slots for 2-1-1 hours pattern
                        if is_slot_available(batch.id, professor.id, day, slot) and slot!=4 and credits>0:
                            available_slots.append((day, slot))
                            break
            elif priority_type == "2-1":
                for day in range(5):
                    for slot in range(8):  # Check up to slot 7 for consecutive slots
                        if slot != 3 and slot !=4:
                            if is_slot_available(batch.id, professor.id, day, slot) and is_slot_available(batch.id, professor.id, day, slot + 1) and slot!=4:
                                available_slots.append((day, slot))
                                break
                credits-=2
                for day in range(5):
                    for slot in range(9):  # Check all slots for 2-1-1 hours pattern
                        if is_slot_available(batch.id, professor.id, day, slot) and slot!=4 and credits>0:
                            available_slots.append((day, slot))
                            break
        else:
            for day in range(5):
                for slot in range(9):
                    if is_slot_available(batch.id, professor.id, day, slot) and slot!=4:
                        available_slots.append((day, slot))
                        break

        if priority and priority_type == "2-hour consecutive":
            if not available_slots:
                flash('Not enough consecutive slots available for priority course', 'error')
            else:
                for _ in range(2):
                    day, start_slot = random.choice(available_slots)
                    classroom = find_available_classroom(day, start_slot)
                    available_slots.remove((day, start_slot))
                    for offset in range(2):
                        new_schedule = Schedule(
                            batch_id=batch.id,
                            course_id=course.id,
                            professor_id=professor.id,
                            day=day,
                            slot=start_slot + offset,
                            classroom_id= classroom.id
                        )
                        db.session.add(new_schedule)
                    try:
                        db.session.commit()
                        flash('Priority course scheduled successfully (2-hour consecutive)', 'success')
                    except:
                        db.session.rollback()
                        flash('Error scheduling priority course (2-hour consecutive)', 'error')
        elif priority and priority_type == "2-1-1":
            if len(available_slots) < credits:
                flash('Not enough available slots for 2-1-1 pattern', 'error')
            else:
                # Step 1: Schedule the 2-hour consecutive slot on one day
                day1, first_slot = available_slots[0]
                classroom = find_available_classroom(day1,first_slot)
                for offset in range(2):  # Schedule 2 consecutive slots
                    new_schedule = Schedule(
                        batch_id=batch.id,
                        course_id=course.id,
                        professor_id=professor.id,
                        day=day1,
                        slot=first_slot + offset,
                        classroom_id= classroom.id
                    )
                    db.session.add(new_schedule)

                # Step 2: Find remaining available slots on different days for 1-hour classes
                day_count = 0
                for day, slot in available_slots[1:]:  # Skip the first day used for 2-hour slot
                    classroom = find_available_classroom(day,slot)
                    if day != day1 and day_count < 2:  # Ensure different days and only 2 additional slots
                        new_schedule = Schedule(
                            batch_id=batch.id,
                            course_id=course.id,
                            professor_id=professor.id,
                            day=day,
                            slot=slot,
                            classroom_id= classroom.id
                        )
                        db.session.add(new_schedule)
                        day_count += 1

                try:
                    db.session.commit()
                    flash('Priority course scheduled successfully (2-1-1)', 'success')
                except:
                    db.session.rollback()
                    flash('Error scheduling priority course (2-1-1)', 'error')
                else:
                    flash('Required slots are not available for the 2-1-1 pattern', 'error')
        elif priority and priority_type == "2-1":
            if len(available_slots) < credits:
                flash('Not enough available slots for 2-1 pattern', 'error')
            else:
                # Step 1: Schedule the 2-hour consecutive slot on one day
                day1, first_slot = available_slots[0]
                classroom = find_available_classroom(day1, first_slot)
                for offset in range(2):  # Schedule 2 consecutive slots
                    new_schedule = Schedule(
                        batch_id=batch.id,
                        course_id=course.id,
                        professor_id=professor.id,
                        day=day1,
                        slot=first_slot + offset,
                        classroom_id= classroom.id
                

                    )
                    db.session.add(new_schedule)

                # Step 2: Find remaining available slots on different days for 1-hour classes
                day_count = 0
                for day, slot in available_slots[1:]:  # Skip the first day used for 2-hour slot
                    classroom = find_available_classroom(day,slot)
                    if day != day1 and day_count < 1:  # Ensure different days and only 1 additional slots
                        new_schedule = Schedule(
                            batch_id=batch.id,
                            course_id=course.id,
                            professor_id=professor.id,
                            day=day,
                            slot=slot,
                            classroom_id= classroom.id
                        )
                        db.session.add(new_schedule)
                        day_count += 1

                try:
                    db.session.commit()
                    flash('Priority course scheduled successfully (2-1)', 'success')
                except:
                    db.session.rollback()
                    flash('Error scheduling priority course (2-1)', 'error')
                else:
                    flash('Required slots are not available for the 2-1 pattern', 'error')
        elif is_lab:
            # Lab scheduling logic remains the same
            if not available_slots:
                flash('Not enough available slots for lab', 'error')
            else:
                day, start_slot = random.choice(available_slots)
                classroom = find_available_classroom(day, start_slot)
                for offset in range(3):
                    new_schedule = Schedule(
                        batch_id=batch.id,
                        course_id=course.id,
                        professor_id=professor.id,
                        day=day,
                        slot=start_slot + offset,
                        classroom_id = classroom.id

                    )
                    db.session.add(new_schedule)
                try:
                    db.session.commit()
                    flash('Lab scheduled successfully', 'success')
                except:
                    db.session.rollback()
                    flash('Error scheduling lab', 'error')

        else:
            if len(available_slots) < credits:
                flash('Not enough available slots', 'error')
            else:
                scheduled_slots = random.sample(available_slots, credits)
                for day, slot in scheduled_slots:
                    classroom = find_available_classroom(day, slot)
                    new_schedule = Schedule(
                        batch_id=batch.id,
                        course_id=course.id,
                        professor_id=professor.id,
                        day=day,
                        slot=slot,
                        classroom_id= classroom.id
                    )
                    db.session.add(new_schedule)
                try:
                    db.session.commit()
                    flash('Course scheduled successfully', 'success')
                except:
                    db.session.rollback()
                    flash('Error scheduling course', 'error')

        return redirect(url_for('manage_batch', batch_id=batch_id))
    schedules = Schedule.query.filter_by(batch_id=batch_id).all()
    timetable = [["-" for _ in range(9)] for _ in range(5)]
    

    for schedule in schedules:
        course = Course.query.get(schedule.course_id)
        professor = Professor.query.get(schedule.professor_id)
        classroom= Classroom.query.get(schedule.classroom_id)
        timetable[schedule.day][schedule.slot] = f"{course.name}({professor.name}), Room: {classroom.name}"

    return render_template('manage_batch.html', batch=batch, timetable=timetable)

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)



