import streamlit as st
import pandas as pd
import pygad
import random

# =========================================================
# PAGE CONFIG
# =========================================================

st.set_page_config(
    page_title="Exam Scheduler",
    layout="wide"
)

st.title("📊 Smart Exam Invigilator Scheduling System")

# =========================================================
# SESSION STATE
# =========================================================

if "final_df" not in st.session_state:
    st.session_state.final_df = None

if "history" not in st.session_state:
    st.session_state.history = []

# =========================================================
# SIDEBAR
# =========================================================

st.sidebar.header("📁 Upload Dataset")

faculty_file = st.sidebar.file_uploader(
    "faculty.csv",
    type=["csv"]
)

hall_file = st.sidebar.file_uploader(
    "exam_hall.csv",
    type=["csv"]
)

availability_file = st.sidebar.file_uploader(
    "availability.csv",
    type=["csv"]
)

student_file = st.sidebar.file_uploader(
    "students.csv",
    type=["csv"]
)

# =========================================================
# MAIN LOGIC
# =========================================================

if faculty_file and hall_file and availability_file and student_file:

    faculty = pd.read_csv(faculty_file)

    halls = pd.read_csv(hall_file)

    availability = pd.read_csv(availability_file)

    students = pd.read_csv(student_file)

    # =====================================================
    # CLEAN COLUMN NAMES
    # =====================================================

    for df in [faculty, halls, availability, students]:
        df.columns = df.columns.str.strip()

    # =====================================================
    # FACULTY DATA
    # =====================================================

    faculty_ids = faculty["Faculty_ID"].tolist()

    faculty_map = {
        i: faculty_ids[i]
        for i in range(len(faculty_ids))
    }

    faculty_dict = faculty.set_index(
        "Faculty_ID"
    ).to_dict("index")

    # =====================================================
    # AVAILABILITY DATA
    # =====================================================

    availability_dict = availability.set_index(
        ["Faculty_ID", "Date", "Time"]
    )["Available"].to_dict()

    # =====================================================
    # ✅ STUDENT ALLOCATION
    # 25 STUDENTS PER FACULTY
    # MAXIMUM 2 FACULTY PER HALL
    # =====================================================

    allocations = []

    grouped = students.groupby(["Date", "Time"])

    for (date, time), day_group in grouped:

        dept_groups = day_group.groupby(
            ["Department", "Subject"]
        )

        dept_queue = []

        for (dept, subject), group in dept_groups:

            group = group.sort_values(
                "Student_ID"
            ).reset_index(drop=True)

            dept_queue.append({
                "Department": dept,
                "Subject": subject,
                "students": group.to_dict("records"),
                "index": 0
            })

        hall_index = 0

        while any(
            d["index"] < len(d["students"])
            for d in dept_queue
        ):

            hall = halls.iloc[
                hall_index % len(halls)
            ]

            hall_id = hall["Hall_ID"]

            hall_capacity = hall["Capacity"]

            filled = 0

            faculty_count = 0

            hall_data = []

            for dept in dept_queue:

                if dept["index"] >= len(dept["students"]):
                    continue

                # Maximum 2 faculty
                if faculty_count >= 2:
                    break

                remaining = (
                    len(dept["students"])
                    - dept["index"]
                )

                # 25 students per faculty
                take = min(
                    remaining,
                    25,
                    hall_capacity - filled
                )

                if take <= 0:
                    continue

                chunk = dept["students"][
                    dept["index"]:
                    dept["index"] + take
                ]

                hall_data.append({

                    "Date": date,
                    "Time": time,
                    "Hall": hall_id,
                    "Department": dept["Department"],
                    "Subject": dept["Subject"],
                    "Students": len(chunk),

                    "Roll Number":
                        f"{chunk[0]['Student_ID']} - "
                        f"{chunk[-1]['Student_ID']}"

                })

                dept["index"] += take

                filled += take

                faculty_count += 1

            allocations.extend(hall_data)

            hall_index += 1

    student_summary_df = pd.DataFrame(allocations)

    # =====================================================
    # SLOT CREATION
    # =====================================================

    slots = []

    grouped_slots = student_summary_df.groupby(
        ["Date", "Time", "Hall"]
    )

    for (date, time, hall), group in grouped_slots:

        faculty_count = 0

        for _, row in group.iterrows():

            if faculty_count >= 2:
                break

            slots.append({
                "Date": date,
                "Time": time,
                "Hall": hall,
                "Department": row["Department"]
            })

            faculty_count += 1

    slots_df = pd.DataFrame(slots)

    # =====================================================
    # GA FUNCTIONS
    # =====================================================

    def repair(solution):

        for i, gene in enumerate(solution):

            fac_id = faculty_map[int(gene)]

            slot = slots_df.iloc[i]

            depts = slot["Department"].split(" + ")

            if (
                faculty_dict[fac_id]["Department"]
                in depts
            ):

                valid = [

                    f for f in faculty_ids

                    if faculty_dict[f]["Department"]
                    not in depts
                ]

                if valid:

                    solution[i] = faculty_ids.index(
                        random.choice(valid)
                    )

        return solution

    def fitness(ga, solution, idx):

        solution = repair(solution)

        penalty = 0

        for i, gene in enumerate(solution):

            fac_id = faculty_map[int(gene)]

            slot = slots_df.iloc[i]

            if availability_dict.get(
                (
                    fac_id,
                    slot["Date"],
                    slot["Time"]
                ),
                "No"
            ) != "Yes":

                penalty += 5

        return 1 / (1 + penalty)

    # =====================================================
    # RUN GA
    # =====================================================

    if st.button("🚀 Run Scheduler"):

        ga = pygad.GA(

            num_generations=20,

            sol_per_pop=10,

            num_parents_mating=4,

            num_genes=len(slots_df),

            gene_space=list(
                range(len(faculty_ids))
            ),

            fitness_func=fitness
        )

        ga.run()

        solution, _, _ = ga.best_solution()

        solution = repair(solution)

        faculty_alloc = []

        for i, gene in enumerate(solution):

            fac_id = faculty_map[int(gene)]

            slot = slots_df.iloc[i]

            faculty_alloc.append({

                "Date": slot["Date"],

                "Time": slot["Time"],

                "Hall": slot["Hall"],

                "Department": slot["Department"],

                "Faculty":
                    faculty_dict[fac_id]["Name"],

                "Faculty_Department":
                    faculty_dict[fac_id]["Department"],

                "Replaced": False
            })

        faculty_df = pd.DataFrame(faculty_alloc)

        expanded = []

        for _, row in faculty_df.iterrows():

            for d in row["Department"].split(" + "):

                expanded.append({

                    "Date": row["Date"],

                    "Time": row["Time"],

                    "Hall": row["Hall"],

                    "Department": d,

                    "Faculty": row["Faculty"],

                    "Faculty_Department":
                        row["Faculty_Department"],

                    "Replaced": False
                })

        expanded_df = pd.DataFrame(expanded)

        final_df = pd.merge(

            student_summary_df,

            expanded_df,

            on=[
                "Date",
                "Time",
                "Hall",
                "Department"
            ],

            how="left"
        )

        st.session_state.final_df = final_df

        st.success("✅ Schedule Generated")

# =========================================================
# DISPLAY
# =========================================================

if st.session_state.final_df is not None:

    df = st.session_state.final_df

    # =====================================================
    # HALL-WISE DISPLAY
    # =====================================================

    st.write("## 🏫 Hall-wise Allocation")

    for hall in sorted(df["Hall"].unique()):

        st.write(f"### 🏫 {hall}")

        hall_df = df[df["Hall"] == hall]

        for session in ["FN", "AN"]:

            temp = hall_df[
                hall_df["Time"] == session
            ]

            if not temp.empty:

                st.write(f"{session} Session")

                st.dataframe(temp)

    # =========================================================
# 🏢 DEPARTMENT-WISE FACULTY DISPLAY
# =========================================================
    if st.session_state.final_df is not None:

        df = st.session_state.final_df

        st.write("## 🏢 Department-wise Faculty Allocation")

    # Select Department
        selected_dept = st.selectbox(
        "Select Department",
        sorted(df["Department"].dropna().unique())
    )

    # Filter Data
        dept_df = df[df["Department"] == selected_dept]

    # Display Result
        st.write(f"### Faculty Assigned for {selected_dept}")

        st.dataframe(
        dept_df[
            [
                "Date",
                "Time",
                "Hall",
                "Department",
                "Faculty",
                "Faculty_Department",
                "Students",
                "Roll Number"
            ]
        ]
    )
# =========================================================
# 🚫 FACULTY REPLACEMENT
# =========================================================

if st.session_state.final_df is not None:

    df = st.session_state.final_df

    st.sidebar.markdown("---")

    st.sidebar.subheader(
        "🚫 Mark Faculty Unavailable"
    )

    dept = st.sidebar.selectbox(

        "Select Faculty Department",

        sorted(
            df["Faculty_Department"]
            .dropna()
            .unique()
        )
    )

    fac_list = df[
        df["Faculty_Department"] == dept
    ]["Faculty"].unique()

    if len(fac_list) > 0:

        fac = st.sidebar.selectbox(
            "Select Faculty",
            sorted(fac_list)
        )

        date = st.sidebar.selectbox(
            "Select Date",
            sorted(df["Date"].unique())
        )

        session = st.sidebar.selectbox(
            "Select Session",
            ["FN", "AN"]
        )

        if st.sidebar.button(
            "Replace Faculty"
        ):

            match = df[

                (df["Faculty"] == fac) &

                (df["Date"] == date) &

                (df["Time"] == session)
            ]

            if match.empty:

                st.sidebar.warning(
                    "No matching assignment found!"
                )

            else:

                for idx in match.index:

                    old = df.loc[idx].copy()

                    dept_row = df.loc[
                        idx,
                        "Department"
                    ]

                    rep = faculty[

                        (
                            faculty["Department"]
                            != dept_row
                        ) &

                        (
                            faculty["Name"]
                            != fac
                        )
                    ]

                    if not rep.empty:

                        new = rep.sample(1).iloc[0]

                        df.at[idx, "Faculty"] = (
                            new["Name"]
                        )

                        df.at[
                            idx,
                            "Faculty_Department"
                        ] = new["Department"]

                        df.at[idx, "Replaced"] = True

                        st.session_state.history.append(
                            old
                        )

                st.sidebar.success(
                    "✅ Faculty Replaced Successfully"
                )

    # =====================================================
    # UNDO REPLACEMENT
    # =====================================================

    if st.sidebar.button(
        "🔁 Undo Last Replacement"
    ):

        if st.session_state.history:

            last = (
                st.session_state.history.pop()
            )

            idx = df[

                (df["Date"] == last["Date"]) &

                (df["Hall"] == last["Hall"]) &

                (
                    df["Department"]
                    == last["Department"]
                )

            ].index

            if len(idx) > 0:

                df.loc[idx[0]] = last

            st.sidebar.success(
                "Undo Successful"
            )

        else:

            st.sidebar.warning(
                "No history available"
            )