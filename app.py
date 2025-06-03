import dropbox
import streamlit as st
from datetime import datetime
from dateutil.relativedelta import relativedelta
import pandas as pd
from fpdf import FPDF
import io

# Load token from secrets.toml
DROPBOX_ACCESS_TOKEN = st.secrets["DROPBOX_ACCESS_TOKEN"]
MEMBER_DIR = "/members"  # Dropbox path

# Dropbox instance
dbx = dropbox.Dropbox(DROPBOX_ACCESS_TOKEN)

def get_current_month():
    return datetime.now().strftime("%b%y").upper()

def format_month(date_obj):
    return date_obj.strftime("%b%y").upper()

def parse_month(month_str):
    return datetime.strptime(month_str, "%b%y")

def generate_next_member_id():
    try:
        res = dbx.files_list_folder(MEMBER_DIR)
        existing_ids = []

        for entry in res.entries:
            if isinstance(entry, dropbox.files.FileMetadata):
                filename = entry.name
                if filename.endswith(".txt") and filename.startswith("RKSC"):
                    try:
                        num = int(filename.replace("RKSC", "").replace(".txt", ""))
                        existing_ids.append(num)
                    except:
                        continue

        next_num = max(existing_ids) + 1 if existing_ids else 1
        return f"RKSC{next_num:04d}"

    except dropbox.exceptions.ApiError as e:
        # If folder doesn't exist, create it and start with ID 0001
        if isinstance(e.error, dropbox.files.ListFolderError) and e.error.is_path():
            dbx.files_create_folder_v2(MEMBER_DIR)
            return "RKSC0001"
        else:
            raise

def create_member(name):
    member_id = generate_next_member_id()
    content = (
        f"Name: {name}\n"
        f"Member ID: {member_id}\n"
        f"Total Paid: 0\n"
        f"Last Payment Month: None\n"
        f"Valid Upto: None\n"
    )
    file_path = f"{MEMBER_DIR}/{member_id}.txt"
    dbx.files_upload(content.encode(), file_path, mode=dropbox.files.WriteMode.overwrite)
    return member_id


def update_payment(member_id, amount):
    file_path = f"{MEMBER_DIR}/{member_id}.txt"

    try:
        metadata, res = dbx.files_download(file_path)
        content = res.content.decode("utf-8")
    except dropbox.exceptions.ApiError:
        st.error("Member not found.")
        return

    lines = content.strip().split("\n")
    data = {line.split(":")[0]: line.split(":")[1].strip() for line in lines if ":" in line}
    months_paid = amount // 20
    now = datetime.now()

    valid_upto_str = data.get("Valid Upto", "None")
    if valid_upto_str == "None":
        new_valid_upto = now + relativedelta(months=months_paid - 1)
    else:
        try:
            last_valid_date = parse_month(valid_upto_str)
            new_valid_upto = last_valid_date + relativedelta(months=months_paid)
        except:
            new_valid_upto = now + relativedelta(months=months_paid - 1)

    data["Total Paid"] = str(int(data.get("Total Paid", 0)) + amount)
    data["Last Payment Month"] = format_month(now)
    data["Valid Upto"] = format_month(new_valid_upto)

    updated_content = "\n".join([f"{key}: {data.get(key, 'None')}" for key in 
                                 ["Name", "Member ID", "Total Paid", "Last Payment Month", "Valid Upto"]])

    dbx.files_upload(updated_content.encode(), file_path, mode=dropbox.files.WriteMode.overwrite)

    st.success(f"₹{amount} added. Valid upto: {format_month(new_valid_upto)}")


def read_member(member_id):
    file_path = f"{MEMBER_DIR}/{member_id}.txt"
    try:
        metadata, res = dbx.files_download(file_path)
        content = res.content.decode("utf-8")
    except dropbox.exceptions.ApiError:
        return None

    member = {}
    for line in content.strip().split("\n"):
        if ":" in line:
            key, value = line.strip().split(":", 1)
            member[key.strip()] = value.strip()
    return member


def list_members():
    members = []
    try:
        res = dbx.files_list_folder(MEMBER_DIR)

        for entry in res.entries:
            if isinstance(entry, dropbox.files.FileMetadata) and entry.name.endswith(".txt"):
                _, res_file = dbx.files_download(entry.path_display)
                content = res_file.content.decode("utf-8")
                data = {line.split(":")[0]: line.split(":")[1].strip() for line in content.split("\n") if ":" in line}
                members.append(data)

    except dropbox.exceptions.ApiError as e:
        st.error("Failed to list members.")
    return members


# def show_due_list():
#     members = list_members()  # Already uses Dropbox
#     now = datetime.now().replace(day=1)
#     dues = []

#     for member in members:
#         valid_upto_str = member.get("Valid Upto", "None")
#         if valid_upto_str == "None":
#             start_month = now
#         else:
#             try:
#                 last_paid_date = parse_month(valid_upto_str)
#                 if last_paid_date >= now:
#                     continue
#                 start_month = last_paid_date + relativedelta(months=1)
#             except:
#                 start_month = now

#         if start_month > now:
#             continue

#         months_due = (now.year - start_month.year) * 12 + (now.month - start_month.month) + 1
#         end_month = now
#         due_period = f"{format_month(start_month)} - {format_month(end_month)}"
#         due_amount = months_due * 20

#         dues.append({
#             "Name": member["Name"],
#             "Member ID": member["Member ID"],
#             "Due Period": due_period,
#             "Due Months": months_due,
#             "Due Amount (INR)": due_amount
#         })

#     if dues:
#         total_months = sum(d["Due Months"] for d in dues)
#         total_amount = sum(d["Due Amount (INR)"] for d in dues)

#         dues.append({
#             "Name": "TOTAL",
#             "Member ID": "",
#             "Due Period": "",
#             "Due Months": total_months,
#             "Due Amount (INR)": total_amount
#         })

#         df = pd.DataFrame(dues)
#         st.dataframe(df, use_container_width=True)

#         if st.button("🖨️ Print to PDF"):
#             output_dir = "due_list"
#             os.makedirs(output_dir, exist_ok=True)

#             month_year_str = now.strftime("%d_%B_%Y")
#             filename = f"duelist_{month_year_str}.pdf"
#             output_path = os.path.join(output_dir, filename)

#             pdf = FPDF()
#             pdf.set_auto_page_break(auto=False)
#             pdf.add_page()
#             pdf.set_font("Arial", "B", 14)
#             pdf.cell(200, 10, f"RKSC Club - Due List ({now.strftime('%d %B %Y')})", ln=True, align='C')

#             pdf.set_font("Arial", "B", 10)
#             headers = ["Name", "Member ID", "Due Period", "Due Months", "Due Amount (INR)"]
#             col_widths = [40, 30, 50, 30, 40]
#             line_height = 10

#             for i, header in enumerate(headers):
#                 pdf.cell(col_widths[i], line_height, header, border=1)
#             pdf.ln(line_height)

#             max_y = 297
#             margin_bottom = 15
#             usable_height = max_y - margin_bottom

#             for row in dues:
#                 if pdf.get_y() + line_height > usable_height:
#                     pdf.add_page()
#                     pdf.set_font("Arial", "B", 10)
#                     for j, header in enumerate(headers):
#                         pdf.cell(col_widths[j], line_height, header, border=1)
#                     pdf.ln(line_height)

#                 if row["Name"] == "TOTAL":
#                     pdf.set_font("Arial", "B", 10)
#                 else:
#                     pdf.set_font("Arial", "", 10)

#                 pdf.cell(col_widths[0], 10, row["Name"], border=1)
#                 pdf.cell(col_widths[1], 10, row["Member ID"], border=1)
#                 pdf.cell(col_widths[2], 10, row["Due Period"], border=1)
#                 pdf.cell(col_widths[3], 10, str(row["Due Months"]), border=1)
#                 pdf.cell(col_widths[4], 10, f"INR {row['Due Amount (INR)']}", border=1)
#                 pdf.ln(line_height)

#             pdf.output(output_path)
#             st.success(f"✅ PDF saved locally as: `{output_path}`")
#     else:
#         st.success("✅ No dues. All members are up to date!")




def show_due_list():
    members = list_members()  # Already uses Dropbox
    now = datetime.now().replace(day=1)

    dues = []

    for member in members:
        valid_upto_str = member.get("Valid Upto", "None")

        if valid_upto_str == "None":
            start_month = now
        else:
            try:
                last_paid_date = parse_month(valid_upto_str)
                if last_paid_date >= now:
                    continue
                start_month = last_paid_date + relativedelta(months=1)
            except:
                start_month = now

        if start_month > now:
            continue

        months_due = (now.year - start_month.year) * 12 + (now.month - start_month.month) + 1
        end_month = now
        due_period = f"{format_month(start_month)} - {format_month(end_month)}"
        due_amount = months_due * 20

        dues.append({
            "Name": member["Name"],
            "Member ID": member["Member ID"],
            "Due Period": due_period,
            "Due Months": months_due,
            "Due Amount (INR)": due_amount
        })

    if dues:
        total_months = sum(d["Due Months"] for d in dues)
        total_amount = sum(d["Due Amount (INR)"] for d in dues)
        dues.append({
            "Name": "TOTAL",
            "Member ID": "",
            "Due Period": "",
            "Due Months": total_months,
            "Due Amount (INR)": total_amount
        })

        df = pd.DataFrame(dues)
        st.dataframe(df, use_container_width=True)

        # Generate PDF in memory
        pdf = FPDF()
        pdf.set_auto_page_break(auto=False)
        pdf.add_page()
        pdf.set_font("Arial", "B", 14)
        pdf.cell(200, 10, f"RKSC Club - Due List ({now.strftime('%d %B %Y')})", ln=True, align='C')

        pdf.set_font("Arial", "B", 10)
        headers = ["Name", "Member ID", "Due Period", "Due Months", "Due Amount (INR)"]
        col_widths = [40, 30, 50, 30, 40]
        line_height = 10

        for i, header in enumerate(headers):
            pdf.cell(col_widths[i], line_height, header, border=1)
        pdf.ln(line_height)

        max_y = 297
        margin_bottom = 15
        usable_height = max_y - margin_bottom

        for row in dues:
            if pdf.get_y() + line_height > usable_height:
                pdf.add_page()
                pdf.set_font("Arial", "B", 10)
                for i, header in enumerate(headers):
                    pdf.cell(col_widths[i], line_height, header, border=1)
                pdf.ln(line_height)

            font_style = "B" if row["Name"] == "TOTAL" else ""
            pdf.set_font("Arial", font_style, 10)
            pdf.cell(col_widths[0], 10, row["Name"], border=1)
            pdf.cell(col_widths[1], 10, row["Member ID"], border=1)
            pdf.cell(col_widths[2], 10, row["Due Period"], border=1)
            pdf.cell(col_widths[3], 10, str(row["Due Months"]), border=1)
            pdf.cell(col_widths[4], 10, f"INR {row['Due Amount (INR)']}", border=1)
            pdf.ln(line_height)

        # Save to BytesIO
        pdf_bytes = pdf.output(dest='S').encode('latin1')
        pdf_buffer = io.BytesIO(pdf_bytes)
        pdf_buffer.seek(0)


        # Offer as download
        st.download_button(
            label="📄 Download Due List PDF",
            data=pdf_buffer,
            file_name=f"duelist_{now.strftime('%d_%B_%Y')}.pdf",
            mime="application/pdf"
        )
    else:
        st.success("✅ No dues. All members are up to date!")


# from fpdf import FPDF
# from io import BytesIO
# from datetime import datetime
# from dateutil.relativedelta import relativedelta

# def show_due_list():
#     now = datetime.now().replace(day=1)
#     dues = []
#     total_due_amount = 0
#     members = list_members()
#     for filename in members:
#         if filename.endswith(".txt"):
#             member_id = filename.replace(".txt", "")
#             member = read_member(member_id)
#             if not member:
#                 continue

#             name = member.get("Name", "Unknown")
#             valid_upto_str = member.get("Valid Upto", "None")

#             if valid_upto_str == "None":
#                 start_month = now
#             else:
#                 try:
#                     last_paid_date = parse_month(valid_upto_str)
#                 except:
#                     continue

#                 if last_paid_date >= now:
#                     continue
#                 start_month = last_paid_date + relativedelta(months=1)

#             if start_month > now:
#                 continue

#             months_due = (now.year - start_month.year) * 12 + (now.month - start_month.month) + 1
#             due_amount = months_due * 20
#             total_due_amount += due_amount

#             due_period = f"{format_month(start_month)} - {format_month(now)}"
#             dues.append({
#                 "Name": name,
#                 "Member ID": member_id,
#                 "Due Period": due_period,
#                 "Due Months": months_due,
#                 "Due Amount (INR)": due_amount
#             })

#     dues = sorted(dues, key=lambda x: x["Name"])
#     dues.append({
#         "Name": "TOTAL",
#         "Member ID": "",
#         "Due Period": "",
#         "Due Months": "",
#         "Due Amount (INR)": total_due_amount
#     })

#     df = pd.DataFrame(dues)
#     st.dataframe(df, use_container_width=True)

#     if st.button("🖨️ Generate PDF Preview"):
#         pdf = FPDF()
#         pdf.set_auto_page_break(auto=False)
#         pdf.add_page()
#         pdf.set_font("Arial", "B", 14)
#         pdf.cell(200, 10, f"RKSC Club - Due List ({now.strftime('%d %B %Y')})", ln=True, align='C')

#         pdf.set_font("Arial", "B", 10)
#         headers = ["Name", "Member ID", "Due Period", "Due Months", "Due Amount (INR)"]
#         col_widths = [40, 30, 50, 30, 40]
#         line_height = 10

#         for i, header in enumerate(headers):
#             pdf.cell(col_widths[i], line_height, header, border=1)
#         pdf.ln(line_height)

#         max_y = 297
#         margin_bottom = 15
#         usable_height = max_y - margin_bottom

#         for row in dues:
#             if pdf.get_y() + line_height > usable_height:
#                 pdf.add_page()
#                 pdf.set_font("Arial", "B", 10)
#                 for j, header in enumerate(headers):
#                     pdf.cell(col_widths[j], line_height, header, border=1)
#                 pdf.ln(line_height)
#                 pdf.set_font("Arial", "", 10)

#             if row.get("Name") == "TOTAL":
#                 pdf.set_font("Arial", "B", 10)
#             else:
#                 pdf.set_font("Arial", "", 10)

#             pdf.cell(col_widths[0], 10, row.get("Name", "Unknown"), border=1)
#             pdf.cell(col_widths[1], 10, row.get("Member ID", ""), border=1)
#             pdf.cell(col_widths[2], 10, row.get("Due Period", ""), border=1)
#             pdf.cell(col_widths[3], 10, str(row.get("Due Months", "")), border=1)
#             pdf.cell(col_widths[4], 10, f"INR {row.get('Due Amount (INR)', 0)}", border=1)
#             pdf.ln(line_height)

#         # Generate PDF as bytes
#         pdf_buffer = BytesIO()
#         pdf.output(pdf_buffer, dest='F')
#         pdf_buffer.seek(0)

#         # Download button
#         st.download_button(
#             label="⬇️ Download PDF",
#             data=pdf_buffer,
#             file_name=f"duelist_{now.strftime('%d_%B_%Y')}.pdf",
#             mime="application/pdf"
#         )



st.markdown("""
    <h1 style='text-align: center; font-size: 2em; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;'>
        💳 RKSC CLUB MEMBERSHIP MANAGER
    </h1>
""", unsafe_allow_html=True)

menu = ["➕ Add New Member", "💰 Record Payment", "📋 View Dues", "👤 Member Account"]
page = st.sidebar.radio("Menu", menu)

# ➕ Add New Member
if page == "➕ Add New Member":
    st.markdown("""
        <h1 style='text-align: center; font-size: 2em; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;'>
            ➕ ADD NEW MEMBER
        </h1>""", unsafe_allow_html=True)
    name = st.text_input("Enter Full Name")
    if st.button("Add Member"):
        if name.strip():
            new_id = create_member(name.strip())
            st.success(f"✅ Member added successfully with ID: `{new_id}`")
        else:
            st.warning("⚠️ Please enter the name.")

# 💰 Record Payment
elif page == "💰 Record Payment":
    st.markdown("""
        <h1 style='text-align: center; font-size: 2em; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;'>
            💰 RECORD MEMBER'S PAYMENTS
        </h1>""", unsafe_allow_html=True)

    member_objs = list_members()
    member_display_list = [f"{m['Member ID']} - {m['Name']}" for m in member_objs]
    member_display_list = sorted(member_display_list)

    selected_member = st.selectbox("Select or search member", [""] + member_display_list)
    amount = st.number_input("Enter Amount (Min ₹20)", min_value=20, step=20)

    if st.button("Submit Payment"):
        if selected_member:
            member_id = selected_member.split()[0]
            update_payment(member_id, amount)
        else:
            st.warning("⚠️ Please select a member.")

# 📋 View Dues
elif page == "📋 View Dues":
    st.markdown("""
        <h1 style='text-align: center; font-size: 2em; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;'>
            📋 MEMBERS WITH DUES
        </h1>""", unsafe_allow_html=True)
    show_due_list()


elif page == "👤 Member Account":
    # Load all members using Dropbox
    member_objs = list_members()
    members_list = [f"{m['Member ID']} - {m.get('Name', 'Unknown')}" for m in member_objs]
    members_list = sorted(members_list)

    selected_member = st.selectbox("Select or search member", [""] + members_list)

    if selected_member:
        member_id = selected_member.split(" - ")[0]

        if st.button("Show Details"):
            member = read_member(member_id)
            if member:
                now = datetime.now().replace(day=1)
                valid_upto_str = member.get("Valid Upto", "None")

                # Handle "up to date" condition
                if valid_upto_str == "None":
                    start_month = now
                else:
                    last_paid_date = parse_month(valid_upto_str)
                    if last_paid_date >= now:
                        due_info = {
                            "Name": member["Name"],
                            "Member ID": member_id,
                            "Last Payment Month": member.get("Last Payment Month", "N/A"),
                            "Valid Upto": member.get("Valid Upto", "N/A"),
                            "Due Period": "No dues",
                            "Due Months": 0,
                            "Due Amount (₹)": 0
                        }
                        df = pd.DataFrame([due_info])
                        st.dataframe(df, use_container_width=True)
                        st.success("✅ Member is up to date.")
                        st.stop()
                    start_month = last_paid_date + relativedelta(months=1)

                # Extra validation: future start date
                if start_month > now:
                    due_info = {
                        "Name": member["Name"],
                        "Member ID": member_id,
                        "Last Payment Month": member.get("Last Payment Month", "N/A"),
                        "Valid Upto": member.get("Valid Upto", "N/A"),
                        "Due Period": "No dues",
                        "Due Months": 0,
                        "Due Amount (₹)": 0
                    }
                    df = pd.DataFrame([due_info])
                    st.dataframe(df, use_container_width=True)
                    st.success("✅ Member is up to date.")
                    st.stop()

                # Calculate due period and amount
                months_due = (now.year - start_month.year) * 12 + (now.month - start_month.month) + 1
                end_month = now
                due_period = f"{format_month(start_month)} - {format_month(end_month)}"
                due_amount = months_due * 20

                due_info = {
                    "Name": member["Name"],
                    "Member ID": member_id,
                    "Last Payment Month": member.get("Last Payment Month", "N/A"),
                    "Valid Upto": member.get("Valid Upto", "N/A"),
                    "Due Period": due_period,
                    "Due Months": months_due,
                    "Due Amount (₹)": due_amount
                }

                df = pd.DataFrame([due_info])
                st.dataframe(df, use_container_width=True)
                st.error("❌ Member has dues.")
            else:
                st.warning("⚠️ Member not found. Please check the ID.")
