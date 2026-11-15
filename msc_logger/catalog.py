"""Illustrative training content, never operational spacecraft procedures."""

TASKS = [
    {
        "id": "filter",
        "name": "Cabin intake inspection",
        "system": "Environmental",
        "interval": 7,
        "last_day": -6,
        "location": "Habitat · Bay A2",
        "steps": [
            "Review the simulated work order and identify the intake unit.",
            "Record visible debris and the condition of the training filter.",
            "Compare the airflow trend with the previous recorded observation.",
            "Document findings and flag anything requiring engineering review.",
        ],
    },
    {
        "id": "treadmill",
        "name": "Exercise harness inspection",
        "system": "Crew equipment",
        "interval": 3,
        "last_day": -3,
        "location": "Habitat · Exercise station",
        "steps": [
            "Confirm that the training equipment is out of use.",
            "Record the visible condition of straps and attachment points.",
            "Record any unusual wear in the maintenance note.",
        ],
    },
    {
        "id": "condensation",
        "name": "Condensation observation",
        "system": "Environmental",
        "interval": 2,
        "last_day": 0,
        "location": "Habitat · Cold-panel zone",
        "steps": [
            "Identify the panel and record the observation time.",
            "Document the extent of visible moisture without disturbing equipment.",
            "Compare humidity readings and record any change.",
        ],
    },
    {
        "id": "battery",
        "name": "Portable equipment check",
        "system": "Crew equipment",
        "interval": 14,
        "last_day": -4,
        "location": "Habitat · Equipment rack",
        "steps": [
            "Record the charge indications on the training devices.",
            "Inspect externally for visible damage.",
            "Record device identifiers and flag any abnormal observation.",
        ],
    },
]

SPARES = [
    ("filter", "Intake filter", "Bay A2 · Filters", 6, 2, "units"),
    ("wipes", "Dry wipes", "Galley · Drawer 1", 120, 20, "units"),
    ("hex", "Hex key set", "Tool kit 3", 2, 1, "sets"),
    ("battery", "Camera battery", "Equipment rack", 8, 2, "units"),
    ("card", "Memory card", "Crew station · Drawer", 5, 2, "units"),
    ("bag", "Waste bag", "Galley · Drawer 2", 30, 5, "units"),
]

# These ranges support software demonstrations, not health or flight decisions.
SENSORS = {
    "airflow": {"name": "Intake airflow", "unit": "%", "base": 94,
                "min": 0, "max": 120, "low": 75, "high": 110},
    "humidity": {"name": "Cabin humidity", "unit": "%", "base": 44,
                 "min": 0, "max": 100, "low": 25, "high": 65},
    "temperature": {"name": "Cabin temperature", "unit": "°C", "base": 22,
                    "min": -50, "max": 100, "low": 18, "high": 28},
}

TREES = {
    "equipment": {
        "title": "Equipment observation",
        "question": "What did you observe?",
        "options": [
            {"label": "Device unresponsive", "steps": [
                "Record device ID, displayed state, and observation time.",
                "Compare the symptom with the approved training procedure.",
                "Record whether the observation persists."], "urgent": False},
            {"label": "Heat, smoke, or unusual smell", "steps": [
                "Stop this training workflow.",
                "Refer to the mission-approved emergency procedure.",
                "Record the event for engineering review when safe."], "urgent": True},
        ],
    },
    "airflow": {
        "title": "Airflow observation",
        "question": "Which symptom is present?",
        "options": [
            {"label": "Low airflow reading", "steps": [
                "Check the reading age and data-quality label.",
                "Compare the trend with a separate training observation.",
                "Document the intake location and observed condition."], "urgent": False},
            {"label": "Unusual fan noise", "steps": [
                "Record the affected unit and symptom.",
                "Refer the observation to engineering."], "urgent": True},
        ],
    },
    "moisture": {
        "title": "Moisture observation",
        "question": "What is visible?",
        "options": [
            {"label": "Condensation on a panel", "steps": [
                "Record the location and visible extent.",
                "Compare humidity and temperature trends.",
                "Document whether the extent changes."], "urgent": False},
            {"label": "Growing leak", "steps": [
                "Stop this training workflow.",
                "Refer to mission-approved emergency procedures.",
                "Record the location and observation when safe."], "urgent": True},
        ],
    },
}
