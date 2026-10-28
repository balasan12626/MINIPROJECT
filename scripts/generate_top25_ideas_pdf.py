"""
AquaSentinel: Top 25 Novel Future Implementation Ideas PDF Generator
Generates a publication-grade, beautifully styled PDF document with
a master summary comparison table (with Difficulty Levels) and comprehensive
technical breakdowns of all 25 ideas.
"""

import os
import sys
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.colors import HexColor
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    KeepTogether, HRFlowable, PageBreak
)
from reportlab.pdfgen import canvas

class NumberedCanvas(canvas.Canvas):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_decorations(num_pages)
            super().showPage()
        super().save()

    def draw_page_decorations(self, page_count):
        self.saveState()
        self.setFont("Helvetica", 8)
        self.setFillColor(HexColor("#64748b"))
        width, height = letter

        # Running header (from page 2 onwards)
        if self._pageNumber > 1:
            self.drawString(40, height - 28, "AquaSentinel | Top 25 Novel Implementation Ideas & Technical Roadmap")
            self.drawRightString(width - 40, height - 28, "CONFIDENTIAL / RESEARCH")
            self.setStrokeColor(HexColor("#cbd5e1"))
            self.setLineWidth(0.5)
            self.line(40, height - 32, width - 40, height - 32)

        # Running footer
        page_str = f"Page {self._pageNumber} of {page_count}"
        self.drawRightString(width - 40, 24, page_str)
        self.drawString(40, 24, "AquaSentinel: Agentic Real-Time Flood Response and Evacuation System")
        self.setStrokeColor(HexColor("#cbd5e1"))
        self.setLineWidth(0.5)
        self.line(40, 34, width - 40, 34)

        self.restoreState()


def get_styles():
    base = getSampleStyleSheet()
    
    styles = {
        "DocTitle": ParagraphStyle(
            "DocTitle",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=22,
            leading=26,
            textColor=HexColor("#0f172a"),
            alignment=0,
            spaceAfter=4,
        ),
        "DocSubtitle": ParagraphStyle(
            "DocSubtitle",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=11,
            leading=15,
            textColor=HexColor("#0284c7"),
            spaceAfter=12,
        ),
        "MetaText": ParagraphStyle(
            "MetaText",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=8.5,
            leading=12,
            textColor=HexColor("#475569"),
        ),
        "SectionHeading": ParagraphStyle(
            "SectionHeading",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=14,
            leading=18,
            textColor=HexColor("#0f172a"),
            spaceBefore=14,
            spaceAfter=8,
            keepWithNext=True,
        ),
        "CategoryHeading": ParagraphStyle(
            "CategoryHeading",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=12,
            leading=16,
            textColor=HexColor("#0369a1"),
            spaceBefore=10,
            spaceAfter=6,
            keepWithNext=True,
        ),
        "IdeaTitle": ParagraphStyle(
            "IdeaTitle",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=11,
            leading=14,
            textColor=HexColor("#0f172a"),
            spaceBefore=8,
            spaceAfter=4,
            keepWithNext=True,
        ),
        "IdeaBody": ParagraphStyle(
            "IdeaBody",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=8.5,
            leading=12,
            textColor=HexColor("#334155"),
            spaceAfter=4,
        ),
        "FieldLabel": ParagraphStyle(
            "FieldLabel",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=8.5,
            leading=12,
            textColor=HexColor("#0f172a"),
        ),
        "TableHeader": ParagraphStyle(
            "TableHeader",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=8,
            leading=10,
            textColor=colors.white,
            alignment=1,
        ),
        "TableCell": ParagraphStyle(
            "TableCell",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=7.5,
            leading=10,
            textColor=HexColor("#1e293b"),
        ),
        "TableCellBold": ParagraphStyle(
            "TableCellBold",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=7.5,
            leading=10,
            textColor=HexColor("#0f172a"),
        ),
        "TableCellCenter": ParagraphStyle(
            "TableCellCenter",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=7.5,
            leading=10,
            textColor=HexColor("#1e293b"),
            alignment=1,
        ),
        "TagEasy": ParagraphStyle(
            "TagEasy",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=7,
            leading=9,
            textColor=HexColor("#15803d"),
            alignment=1,
        ),
        "TagMedium": ParagraphStyle(
            "TagMedium",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=7,
            leading=9,
            textColor=HexColor("#b45309"),
            alignment=1,
        ),
        "TagHard": ParagraphStyle(
            "TagHard",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=7,
            leading=9,
            textColor=HexColor("#b91c1c"),
            alignment=1,
        ),
        "TagExpert": ParagraphStyle(
            "TagExpert",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=7,
            leading=9,
            textColor=HexColor("#6d28d9"),
            alignment=1,
        ),
    }
    return styles


TOP_25_DATA = [
    # Category 1: Multi-Modal AI & Edge Intelligence
    {
        "id": 1,
        "title": "Computer Vision Water-Depth Estimation from Citizen SOS Photos",
        "category": "Multi-Modal AI & Edge",
        "difficulty": "Medium",
        "est_time": "3-4 days",
        "impact": "Converts qualitative citizen photos into calibrated physical water depth (cm)",
        "problem": "Citizen SOS reports say 'water is high', which is subjective and uncalibrated. Rescue dispatchers cannot verify whether roads are passable by standard ambulances (clearance ≤30cm) or require heavy trucks/boats.",
        "concept": "When users upload a photo via /sos (F4), an onboard vision model (Florence-2 / YOLOv8-seg) detects reference anchors with standardized real-world dimensions (car tire rim=60cm, car door handle=90cm, human knee=50cm, lamppost base). Computes metric water depth in centimeters.",
        "architecture": "backend/services/cv_water_depth.py runs asynchronous photo inference; estimates depth in cm and confidence interval; updates road flood blockage directly if photo geotag aligns with an active road edge.",
        "tech_stack": "Ultralytics YOLOv8-seg / Florence-2 ONNX, OpenCV, Pillow EXIF coordinate parser, Leaflet image marker popups.",
    },
    {
        "id": 2,
        "title": "Acoustic Disaster Intelligence: Audio Analysis in SOS Calls",
        "category": "Multi-Modal AI & Edge",
        "difficulty": "Medium",
        "est_time": "2-3 days",
        "impact": "Identifies urgent panic, structural collapse, and rushing water from ambient sound",
        "problem": "Trapped victims in dark attics, under rubble, or with failing eyesight cannot type text. GPS may be degraded indoors, leaving dispatchers blind to immediate life-threat severity.",
        "concept": "Allows the citizen SOS page and voice agent to record a 5-second ambient sound burst. An audio transformer (AST / YAMNet) detects acoustic hazard signatures: rushing torrents, screaming/crying, structural cracking, or motorboat hums.",
        "architecture": "POST /api/public/sos/audio passes WAV buffer to torch-audio/ONNX classifier; updates triage priority in person_ops.py with ACOUSTIC_DISTRESS_WEIGHT multiplier (up to 1.8x).",
        "tech_stack": "YAMNet / Audio Spectrogram Transformer (AST), PyTorch / ONNX Runtime, Web Audio API recorder, Recharts audio waveform.",
    },
    {
        "id": 3,
        "title": "Automated Counterfactual Explanations ('Recourse Engine')",
        "category": "Multi-Modal AI & Edge",
        "difficulty": "Medium-Hard",
        "est_time": "3-4 days",
        "impact": "Answers 'What exact intervention would rescue Person X 20 minutes earlier?'",
        "problem": "Current XAI explains why an action happened (F13), but gives zero guidance on how an incident commander can proactively change an unacceptable delay.",
        "concept": "Computes actionable counterfactual recourse: uses the virtual-clock simulator (ops_sim.py) to perturb single operational constraints (freeing an ambulance 5 min earlier, clearing a specific road choke point) to find the minimal required intervention.",
        "architecture": "backend/services/recourse.py runs bounded perturbation search over live snapshot state; outputs clean bulleted recommendations for the dispatcher.",
        "tech_stack": "ops_sim.py digital twin core, SciPy optimization, DecisionCard.jsx expandable intervention drawer.",
    },
    {
        "id": 4,
        "title": "Real-Time Multimodal Satellite SAR (Sentinel-1) Inundation Mask",
        "category": "Multi-Modal AI & Edge",
        "difficulty": "Hard",
        "est_time": "4-6 days",
        "impact": "Automated satellite radar flood mapping through thick monsoonal clouds",
        "problem": "Optical satellite images are useless during monsoons due to thick cloud cover. Manual GIS shapefile ingestion is too slow during rapid flood onset.",
        "concept": "Connects to Copernicus Data Space Ecosystem / Microsoft Planetary Computer STAC API to pull fresh Sentinel-1 SAR (Synthetic Aperture Radar) Ground Range Detected (GRD) tiles. Automatically applies Lee filter and Otsu water thresholding.",
        "architecture": "scripts/fetch_live_sar.py fetches GeoTIFFs; rasterizer aligns with city bounding box; generates vector flood polygon layer for LiveRescueMap.jsx.",
        "tech_stack": "Copernicus STAC API, Sentinel-1 VV/VH radar backscatter, rasterio / pure-numpy thresholding, Leaflet GeoJSON layer.",
    },
    {
        "id": 5,
        "title": "AI Dispatcher Dialect & Panic-Resilient Voice Interface",
        "category": "Multi-Modal AI & Edge",
        "difficulty": "Medium-Hard",
        "est_time": "3-5 days",
        "impact": "Extracts critical triage slots from panicked, dialect-heavy regional speech",
        "problem": "In panic, callers shout colloquial phrases ('paani kamar tak hai', 'chhat par hain') in local dialects (Bhojpuri, Assamese, colloquial Tamil) that generic English/Hindi bots fail to understand.",
        "concept": "Fine-tuned Whisper-Indic speech-to-text with prompt-guided slot filling (landmark, headcount, water height relative to body parts, urgent medical conditions). Automatically creates structured SOS records without human dispatcher intervention.",
        "architecture": "POST /api/voice/webhook handles audio streams, runs Whisper-base Indic model, extracts JSON slots, calls add_citizen_sos() with provenance tag.",
        "tech_stack": "Whisper-Indic, Groq LLaMA JSON slot extraction, WebRTC audio recorder, Twilio / browser speech client.",
    },

    # Category 2: Advanced Logistics & Autonomous Swarms
    {
        "id": 6,
        "title": "UAV / Drone Swarm Reconnaissance Routing & Battery Constraints",
        "category": "Logistics & Swarms",
        "difficulty": "Hard",
        "est_time": "4-5 days",
        "impact": "Autonomous aerial scouts verify unconfirmed flooded roads before ambulances deploy",
        "problem": "Ambulances often drive 15 minutes only to find an unmapped local blockage, forcing expensive turnaround and delaying critical patient care.",
        "concept": "Deploys an autonomous drone reconnaissance swarm from fire depots. Drones fly ahead to inspect uncertain road links (conformal uncertainty > threshold) subject to battery discharge and headwind models.",
        "architecture": "backend/services/drone_ops.py solves Vehicle Routing Problem with Drone (VRPD); clears or confirms road blockages; renders drone flight paths and camera cones on map.",
        "tech_stack": "VRPD solver with battery discharge curves, NetworkX, Leaflet animated radar sweep canvas.",
    },
    {
        "id": 7,
        "title": "Multi-Modal Transfer Points (Ambulance ⇄ Boat Intermodal Hubs)",
        "category": "Logistics & Swarms",
        "difficulty": "Medium",
        "est_time": "2-3 days",
        "impact": "Chains boat extraction in water with ambulance transport on dry land",
        "problem": "Boats cannot drive on dry roads to reach hospitals; ambulances cannot enter 2-meter deep water. Currently, rescue plans are forced into a single vehicle type.",
        "concept": "Creates dynamic Intermodal Transfer Hubs at the waterline. A rescue boat extracts victims from submerged rooftops to the transfer hub, where a synchronized ambulance receives the patient for hospital transport.",
        "architecture": "Bi-modal Dijkstra graph in person_ops.py: Leg 1 (Boat on water grid) + Handover delay (3 min) + Leg 2 (Ambulance on road network). Synchronizes arrival times to avoid patient exposure.",
        "tech_stack": "person_ops.py multi-leg stage machine, boat_route.py, Leaflet dual-colored multi-segment polylines.",
    },
    {
        "id": 8,
        "title": "Mobile Refueling & Fast-Charging Tanker Fleet Scheduling",
        "category": "Logistics & Swarms",
        "difficulty": "Medium",
        "est_time": "2-3 days",
        "impact": "Refuels rescue vehicles in field sectors without returning to distant home depots",
        "problem": "Floods submerge gas stations. Under F25 crew rules, ambulances must drive all the way back to their home depot to refuel, wasting up to 40% of their operational shift.",
        "concept": "Mobile Fuel and Power Tankers navigate open road corridors to rendezvous with low-fuel ambulances or power critical shelter backup generators on site.",
        "architecture": "backend/services/fuel_logistics.py tracks fuel burn rate (L/km adjusted for water resistance); dispatches mobile tankers using Capacitated Vehicle Routing Problem (CVRP).",
        "tech_stack": "CVRP solver, FleetPanel.jsx battery/diesel fuel gauges, mobile tanker asset markers.",
    },
    {
        "id": 9,
        "title": "Heavy Machinery (JCB/Bulldozer) Debris Clearance Dispatch",
        "category": "Logistics & Swarms",
        "difficulty": "Medium",
        "est_time": "2-3 days",
        "impact": "Optimal scheduling of excavators to reopen roads based on network connectivity gain",
        "problem": "Receding floodwaters leave roads blocked by silt, fallen trees, and stalled vehicles. Clearing crews currently work randomly rather than prioritizing roads that unlock the most people.",
        "concept": "Formulates road reopening as a Network Connectivity Restoration Problem. Schedules JCBs/bulldozers to clear blockages that maximize the number of reconnected cut-off citizens per work-hour.",
        "architecture": "Betweenness centrality and cut-off population demand weighting in backend/services/clearance.py; outputs a real-time unblocking queue with countdown timers.",
        "tech_stack": "Graph centrality algorithms, NetworkX, RoadControlPanel.jsx clearance crew cards.",
    },
    {
        "id": 10,
        "title": "Dynamic Supply Airdrop Optimization for Inaccessible Rooftops",
        "category": "Logistics & Swarms",
        "difficulty": "Easy-Medium",
        "est_time": "1-2 days",
        "impact": "Calculates emergency airdrop packages for citizens stranded with zero road/boat access",
        "problem": "When both roads and waterways are completely impassable, stranded citizens run out of food and insulin while awaiting rescue, leading to preventable fatalities.",
        "concept": "Identifies isolated clusters where time-to-rescue exceeds critical survival thresholds (>12 hours). Calculates payload allocations (water tablets, high-energy biscuits, emergency medications) for helicopter/drone drops.",
        "architecture": "Extends backend/services/supply.py with aerial payload clustering; adds airdrop marker and survival time extension (+24h) to person log rows.",
        "tech_stack": "K-Means geospatial clustering, supply.py Sphere WASH logic, parachute drop icons on map.",
    },

    # Category 3: Physics, Hydrology & Infrastructure Cascades
    {
        "id": 11,
        "title": "Physics-Informed 2D Hydrodynamic Surface Inundation (PINN)",
        "category": "Physics & Hydrology",
        "difficulty": "Advanced / Expert",
        "est_time": "5-7 days",
        "impact": "Sub-second 2D shallow water equation surrogate replacing empirical distance proxies",
        "problem": "Traditional 2D hydrodynamic models (HEC-RAS, LISFLOOD) require hours to run, making real-time digital twin prediction impossible.",
        "concept": "A trained Physics-Informed Neural Network (PINN) or Fourier Neural Operator surrogate predicts continuous 2D water depth and flow velocity vectors across city DEMs in sub-second inference time.",
        "architecture": "backend/ml/hydro_pinn.py runs ONNX model taking elevation, rain rate, and river discharge; outputs water depth grid; closes roads when depth > vehicle clearance threshold.",
        "tech_stack": "PyTorch / ONNX, Navier-Stokes / Shallow Water 2D equations, WebGL fluid depth canvas layer.",
    },
    {
        "id": 12,
        "title": "Cascading Power Grid Failure & Substation Submersion Modeling",
        "category": "Physics & Hydrology",
        "difficulty": "Medium",
        "est_time": "2-3 days",
        "impact": "Simulates interdependent power blackout zones, hospital generator limits, and tower losses",
        "problem": "Floods do not just submerge roads; they knock out electrical substations, cutting power to hospitals, sewage pump stations, cellular towers, and water filtration plants.",
        "concept": "Models electrical grid dependency topology. If a substation floods, dependent zones enter blackout status: hospital emergency generators start a countdown, water pumps stop, and cell towers fail.",
        "architecture": "backend/services/infrastructure_cascade.py maps OSM power=substation to city sectors; triggers fuel requests (F28) for hospital generators; halves nighttime vehicle speeds in blackouts.",
        "tech_stack": "Topological dependency DAG, OSM Overpass power tags, blackout polygon overlays.",
    },
    {
        "id": 13,
        "title": "Dynamic Sandbag / Micro-Barrier Placement Optimization (MILP)",
        "category": "Physics & Hydrology",
        "difficulty": "Medium-Hard",
        "est_time": "3-4 days",
        "impact": "Recommends exact riverbank barrier locations to prevent flooding of critical hospitals",
        "problem": "Disaster managers possess limited sandbags and mobile flood pumps, but place them ad-hoc without knowing which barrier segments preserve the most critical infrastructure.",
        "concept": "Mixed-Integer Linear Programming (MILP) solver that determines the optimal placement of temporary barriers along riverbanks to prevent water breach into high-value assets (hospitals, shelters, main bridges).",
        "architecture": "backend/optimization/barrier_milp.py solves knapsack-constrained barrier allocation; adds interactive barrier placement tool in Scenario builder.",
        "tech_stack": "PuLP / SciPy MILP solver, ScenarioContext.jsx barrier simulation controls.",
    },
    {
        "id": 14,
        "title": "Dam Inflow Hydrograph Forecasting with Reservoir Rule-Curves",
        "category": "Physics & Hydrology",
        "difficulty": "Medium",
        "est_time": "2-3 days",
        "impact": "Dynamic spillway discharge optimization balancing dam safety against urban inundation",
        "problem": "Sudden emergency spillway releases by upstream dams trigger catastrophic flash floods in downstream cities (e.g. Yamuna in Delhi, Mithi in Mumbai).",
        "concept": "Connects upstream catchment rainfall forecasts to dam reservoir inflow hydrographs using the SCS-CN hydrological method. Optimizes gate opening schedules against statutory rule curves to prevent downstream surges.",
        "architecture": "backend/services/dam_inflow.py computes 18-hour ahead inflow forecasts; recommends graduated release rates; warns downstream MAS agents 6 hours in advance.",
        "tech_stack": "SCS-CN unit hydrograph equation, dam_risk.py, Recharts reservoir inflow/outflow graph.",
    },
    {
        "id": 15,
        "title": "Real-Time Economic Damage & Loss Estimation Engine",
        "category": "Physics & Hydrology",
        "difficulty": "Easy-Medium",
        "est_time": "1-2 days",
        "impact": "Calculates real-time financial damage (in ₹ Crores) using JRC Depth-Damage Curves",
        "problem": "Municipal authorities and disaster relief funds lack instantaneous objective financial damage figures during the disaster, delaying emergency state aid packages.",
        "concept": "Applies international Depth-Damage vulnerability curves (JRC / HAZUS) to flooded building footprints (residential, commercial, industrial) to compute financial loss in real time as floodwaters rise.",
        "architecture": "backend/services/economic_loss.py matches flood depth at building centroid with structural vulnerability functions; aggregates total loss and uninsured losses.",
        "tech_stack": "JRC Global Flood Depth-Damage functions, OSM building classification, ScenarioOutputs KPI tiles.",
    },

    # Category 4: Communications, Mesh Networks & Decentralization
    {
        "id": 16,
        "title": "WebRTC / BLE Peer-to-Peer Offline SOS Mesh Relay",
        "category": "Communications & Mesh",
        "difficulty": "Hard",
        "est_time": "4-5 days",
        "impact": "Transmits citizen SOS packets hop-by-hop through phones when cell towers are destroyed",
        "problem": "In F29 silent zones, mobile towers are dead. Even with an offline SOS outbox (F15), the packet remains trapped on the phone until that specific user physically walks to a working tower.",
        "concept": "Browser-to-browser Delay-Tolerant Networking (DTN). Phones physically carry encrypted SOS packets from neighbors and relay them via WebRTC DataChannels / BLE to passing citizens until someone reaches cellular coverage.",
        "architecture": "Service Worker background sync + WebRTC peer discovery; bundles forward at /api/public/sos/mesh-sync; tracks hop counts, latency, and mesh topology.",
        "tech_stack": "WebRTC DataChannel API, IndexedDB packet cache, cryptographic message hashes, mesh visualizer.",
    },
    {
        "id": 17,
        "title": "National Disaster Management (NDMA / CAP-v1.2) Alert Message Broker",
        "category": "Communications & Mesh",
        "difficulty": "Easy",
        "est_time": "1-2 days",
        "impact": "Broadcasts official Common Alerting Protocol (CAP) XML feeds to government agencies",
        "problem": "Municipal flood alerts are trapped inside local dashboards and cannot feed into national telecom cell-broadcast systems (e.g. NDMA SACHET, Google Public Alerts).",
        "concept": "Implements standard OASIS Common Alerting Protocol (CAP-v1.2) XML feeds. Exposes authenticated endpoints allowing state disaster agencies to ingest AquaSentinel zone evacuation warnings directly.",
        "architecture": "GET /api/cap/feed.atom and POST /api/cap/alert endpoints; formats zone warnings with WKT polygons, severity, urgency, and bilingual alert text.",
        "tech_stack": "OASIS CAP v1.2 XML standard, Python lxml / xmltodict, Atom 1.0 feed generator.",
    },
    {
        "id": 18,
        "title": "Zero-Knowledge Verifiable Volunteer & Civilian Rescuer Credentialing",
        "category": "Communications & Mesh",
        "difficulty": "Medium-Hard",
        "est_time": "3-4 days",
        "impact": "Verifies civilian boat operators, doctors, and amateur radio volunteers safely",
        "problem": "Spontaneous civilian volunteers flood emergency zones. Dispatchers have no way to verify credentials (valid boat license, registered nurse) without bureaucratic delays or privacy breaches.",
        "concept": "Issues cryptographic W3C Verifiable Credentials (Ed25519 signatures). Volunteers present QR-coded cryptographic proofs of qualification, allowing dispatchers to assign appropriate tasks instantly.",
        "architecture": "backend/services/volunteer_auth.py verifies digital signatures; adds verified civilian fleet units to fleet board with restricted task roles.",
        "tech_stack": "Ed25519 cryptography, W3C Verifiable Credentials, QR code scanner on mobile portal.",
    },
    {
        "id": 19,
        "title": "Crowdsourced Water-Level Gauge Calibration via AR / QR Street Markers",
        "category": "Communications & Mesh",
        "difficulty": "Medium",
        "est_time": "2-3 days",
        "impact": "Turns lampposts and bridge piers into precision water gauges via smartphone cameras",
        "problem": "Cities have very few official river gauges (only 1 in Delhi; none in Chennai/Mumbai). Micro-level street water rise is unmeasured.",
        "concept": "Citizens scan pre-surveyed QR reference markers or high-water signs on lampposts and walls. The web app uses WebXR / camera geometry to measure the vertical pixel distance to the water surface.",
        "architecture": "Frontend AR camera canvas measures marker-to-waterline ratio; submits micro-gauge reading to /api/public/gauge-report; ingests into hydrological engine.",
        "tech_stack": "WebXR / HTML5 Canvas API, OpenCV.js marker detection, GeoJSON micro-gauge layer.",
    },

    # Category 5: Human Factors, Public Health & Socio-Economic Equity
    {
        "id": 20,
        "title": "Shelter Epidemic & Water-Borne Disease Outbreak Forecaster (WASH)",
        "category": "Human Factors & Health",
        "difficulty": "Easy-Medium",
        "est_time": "1-2 days",
        "impact": "Predicts Cholera, Leptospirosis, and Dengue outbreak risks inside crowded shelters",
        "problem": "During prolonged floods, secondary casualties from water-borne epidemics in overcrowded, unsanitary shelters often exceed direct drowning deaths.",
        "concept": "Integrates an epidemiological SEIR-WASH disease transmission model predicting outbreak probabilities based on shelter population density (m²/person, F27), potable water availability (L/day, F28), and stay duration.",
        "architecture": "backend/services/epidemic_risk.py computes daily R0 for Cholera, Leptospirosis, and Dengue; triggers urgent medical supply trucks before symptomatic outbreaks occur.",
        "tech_stack": "SEIR-WASH differential equations, Sphere WASH standards, ShelterCapacityPanel health risk meter.",
    },
    {
        "id": 21,
        "title": "Special-Needs Registry with Privacy-Preserving Enclaves",
        "category": "Human Factors & Health",
        "difficulty": "Medium",
        "est_time": "2-3 days",
        "impact": "Guarantees dialysis, oxygen-dependent, and bedridden patients reach specialized facilities",
        "problem": "Standard triage categorizes people simply as 'elderly' or 'child'. Oxygen-dependent or dialysis patients dispatched to school gym shelters die due to lack of electricity.",
        "concept": "Privacy-preserving pre-registration for vulnerable citizens with specific medical dependencies. Data remains encrypted until an evacuation warning hits their zone; Hungarian matching enforces hard destination constraints.",
        "architecture": "AES-256 encrypted fields in citizen schema; person_ops.py applies hard constraints routing oxygen/dialysis patients exclusively to hospitals with verified emergency power.",
        "tech_stack": "Cryptography Fernet / AES-256, Scipy Hungarian matching constraints, People table alert badges.",
    },
    {
        "id": 22,
        "title": "Adversarial Red-Team Agent ('Chaos Disaster Monkey')",
        "category": "Human Factors & Health",
        "difficulty": "Hard",
        "est_time": "4-5 days",
        "impact": "Discovers hidden catastrophic failure cascades by injecting worst-case multi-point shocks",
        "problem": "Simulations usually test standard, predictable scenarios. Planners remain completely oblivious to catastrophic compound failures (e.g. cloudburst + bridge collapse + generator failure).",
        "concept": "An automated AI Adversary Agent that actively searches for the combination of shocks that maximizes evacuation failure and regret within a constrained disaster budget.",
        "architecture": "backend/services/adversary_agent.py uses genetic algorithms / Monte Carlo tree search to discover the city's top 5 most vulnerable failure choke points.",
        "tech_stack": "Monte Carlo Tree Search (MCTS), ops_sim.py digital twin, vulnerability heatmaps.",
    },
    {
        "id": 23,
        "title": "Real-Time Traffic Gridlock & Spontaneous Self-Evacuation Simulator",
        "category": "Human Factors & Health",
        "difficulty": "Hard",
        "est_time": "4-5 days",
        "impact": "Models civilian panic traffic jams that slow rescue ambulances down to 5 km/h",
        "problem": "In real floods, ambulances do not travel on empty streets. Panic self-evacuation by thousands of private cars creates gridlock on all outbound arterial routes.",
        "concept": "Macroscopic Fundamental Diagram (MFD) traffic flow model. When an evacuation warning is broadcast, citizen vehicle density surges on escape routes, dynamically slowing ambulance travel speeds.",
        "architecture": "backend/services/traffic_flow.py updates road travel times as a function of volume-to-capacity ratio; router identifies bypass contra-flow corridors for emergency fleets.",
        "tech_stack": "BPR (Bureau of Public Roads) / MFD traffic flow equations, NetworkX edge weights, traffic congestion heatmap.",
    },
    {
        "id": 24,
        "title": "Multi-Agent Reinforcement Learning (MARL) for Fleet Pre-Positioning",
        "category": "Human Factors & Health",
        "difficulty": "Advanced / Expert",
        "est_time": "5-7 days",
        "impact": "Autonomous agents learn proactive spatial staging strategies anticipating flood evolution",
        "problem": "Heuristic k-median pre-positioning (F9) is reactive and static. It cannot anticipate when an escape bridge is about to close 20 minutes in the future.",
        "concept": "Multi-Agent Deep Reinforcement Learning (MADRL / QMIX). Ambulance agents learn cooperative staging strategies, preemptively crossing vulnerable river bridges before they submerge.",
        "architecture": "Gymnasium environment wrapping ops_sim.py; trained QMIX / MAPPO neural policy; benchmarked against heuristic baseline on time-to-safety across 6 cities.",
        "tech_stack": "PettingZoo / Gymnasium, PyTorch RL, ops_sim.py environment, Algorithms tab MARL card.",
    },
    {
        "id": 25,
        "title": "Digital Twin After-Action Review (AAR) & Policy Learning Dashboard",
        "category": "Human Factors & Health",
        "difficulty": "Medium",
        "est_time": "2-3 days",
        "impact": "Automated LLM synthesis of municipal resilience investments (e.g. where to build sea walls)",
        "problem": "After a flood, post-incident debriefs take months and rely on fallible human memory, resulting in repeated municipal mistakes year after year.",
        "concept": "Automated Executive After-Action Report (AAR) engine. Analyzes all agent transcripts, regret metrics (F34), equity scores (F14), and bottlenecks to output high-level infrastructure investment recommendations.",
        "architecture": "backend/services/aar_generator.py synthesizes run history into structured JSON; Groq LLaMA formats executive takeaways, bottleneck diagnosis, and ROI on proposed civil works.",
        "tech_stack": "Groq LLaMA, ReportLab / PDF export, Recharts investment return comparison chart.",
    },
]


def build_pdf(filename="AquaSentinel_Top25_Future_Ideas.pdf"):
    doc = SimpleDocTemplate(
        filename,
        pagesize=letter,
        leftMargin=40,
        rightMargin=40,
        topMargin=42,
        bottomMargin=42,
    )
    
    styles = get_styles()
    story = []

    # -------------------------------------------------------------
    # COVER / HEADER BANNER
    # -------------------------------------------------------------
    story.append(Paragraph("AQUASENTINEL: AGENTIC FLOOD TWIN", styles["DocSubtitle"]))
    story.append(Paragraph("Top 25 Novel Implementation Ideas & Research Roadmap", styles["DocTitle"]))
    story.append(Paragraph(
        "<b>Document Version:</b> 2.0-PROPOSAL &nbsp;|&nbsp; <b>Scope:</b> Future Roadmap (Beyond F1–F37) &nbsp;|&nbsp; <b>Domain:</b> Multi-Agent Decision Systems, Urban Hydrology & Multi-Modal Logistics",
        styles["MetaText"]
    ))
    story.append(Spacer(1, 10))
    story.append(HRFlowable(width="100%", thickness=1.5, color=HexColor("#0284c7"), spaceAfter=14))

    # Executive Overview Callout Box
    overview_text = (
        "<b>Executive Overview:</b> Following the successful deployment and benchmarking of core features "
        "F1 through F34 (including Hungarian dispatch, Dijkstra/QAOA routing, CWC river telemetry, Open-Meteo forecasts, "
        "WorldPop grids, Sentinel-1 satellite validation, and Sphere standard logistics), this roadmap introduces "
        "<b>25 groundbreaking, publishable, and implementable extensions</b>. These proposals span edge computer vision, "
        "physics-informed neural operators (PINNs), offline WebRTC mesh relays, intermodal transfer logistics, "
        "and multi-agent reinforcement learning (MARL). Every item is categorized, evaluated by difficulty level, and "
        "provided with complete architectural blueprints."
    )
    overview_table = Table(
        [[Paragraph(overview_text, styles["IdeaBody"])]],
        colWidths=[532],
    )
    overview_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), HexColor("#f0f9ff")),
        ('BOX', (0, 0), (-1, -1), 1, HexColor("#bae6fd")),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('LEFTPADDING', (0, 0), (-1, -1), 12),
        ('RIGHTPADDING', (0, 0), (-1, -1), 12),
    ]))
    story.append(overview_table)
    story.append(Spacer(1, 16))

    # -------------------------------------------------------------
    # MASTER COMPARISON TABLE (ALL 25 IDEAS WITH DIFFICULTY)
    # -------------------------------------------------------------
    story.append(Paragraph("Master Comparison & Difficulty Classification Matrix", styles["SectionHeading"]))
    story.append(Paragraph(
        "Comprehensive matrix summarizing all 25 novel proposals, their thematic categories, estimated implementation duration, "
        "difficulty classification, and primary operational or scientific breakthrough.",
        styles["IdeaBody"]
    ))
    story.append(Spacer(1, 6))

    # Table columns: ID (22), Title (140), Category (95), Difficulty (65), Est Time (55), Primary Value (155) = 532 pt
    table_data = [[
        Paragraph("<b>#</b>", styles["TableHeader"]),
        Paragraph("<b>Proposed Novel Feature</b>", styles["TableHeader"]),
        Paragraph("<b>Thematic Domain</b>", styles["TableHeader"]),
        Paragraph("<b>Difficulty</b>", styles["TableHeader"]),
        Paragraph("<b>Dev Time</b>", styles["TableHeader"]),
        Paragraph("<b>Core Impact & Academic Value</b>", styles["TableHeader"]),
    ]]

    for item in TOP_25_DATA:
        diff = item["difficulty"]
        if "Easy" in diff and "Medium" not in diff:
            diff_style = styles["TagEasy"]
        elif "Medium" in diff and "Hard" not in diff:
            diff_style = styles["TagMedium"]
        elif "Hard" in diff and "Expert" not in diff and "Medium-Hard" not in diff:
            diff_style = styles["TagHard"]
        elif "Expert" in diff:
            diff_style = styles["TagExpert"]
        else:
            diff_style = styles["TagMedium"]

        table_data.append([
            Paragraph(f"<b>{item['id']}</b>", styles["TableCellCenter"]),
            Paragraph(f"<b>{item['title']}</b>", styles["TableCellBold"]),
            Paragraph(item["category"], styles["TableCell"]),
            Paragraph(item["difficulty"], diff_style),
            Paragraph(item["est_time"], styles["TableCellCenter"]),
            Paragraph(item["impact"], styles["TableCell"]),
        ])

    matrix_table = Table(
        table_data,
        colWidths=[20, 138, 90, 68, 56, 160],
        repeatRows=1,
    )
    matrix_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), HexColor("#0f172a")),
        ('GRID', (0, 0), (-1, -1), 0.5, HexColor("#cbd5e1")),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 3.5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3.5),
        ('LEFTPADDING', (0, 0), (-1, -1), 4),
        ('RIGHTPADDING', (0, 0), (-1, -1), 4),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, HexColor("#f8fafc")]),
    ]))
    story.append(matrix_table)
    story.append(Spacer(1, 14))
    story.append(PageBreak())

    # -------------------------------------------------------------
    # DETAILED BREAKDOWNS OF ALL 25 IDEAS
    # -------------------------------------------------------------
    categories = [
        ("Multi-Modal AI & Edge Intelligence", [1, 2, 3, 4, 5]),
        ("Advanced Logistics & Autonomous Swarms", [6, 7, 8, 9, 10]),
        ("Physics, Hydrology & Infrastructure Cascades", [11, 12, 13, 14, 15]),
        ("Communications, Mesh Networks & Decentralization", [16, 17, 18, 19]),
        ("Human Factors, Public Health & Socio-Economic Equity", [20, 21, 22, 23, 24, 25]),
    ]

    for cat_name, item_ids in categories:
        story.append(Paragraph(f"Category: {cat_name}", styles["CategoryHeading"]))
        story.append(HRFlowable(width="100%", thickness=0.75, color=HexColor("#0284c7"), spaceAfter=8))

        cat_items = [x for x in TOP_25_DATA if x["id"] in item_ids]
        for itm in cat_items:
            # Card block for each idea
            diff = itm["difficulty"]
            if "Easy" in diff and "Medium" not in diff:
                badge_bg = HexColor("#dcfce7")
                badge_border = HexColor("#86efac")
                badge_text = HexColor("#15803d")
            elif "Medium" in diff and "Hard" not in diff:
                badge_bg = HexColor("#fef3c7")
                badge_border = HexColor("#fde68a")
                badge_text = HexColor("#b45309")
            elif "Hard" in diff and "Expert" not in diff and "Medium-Hard" not in diff:
                badge_bg = HexColor("#fee2e2")
                badge_border = HexColor("#fca5a5")
                badge_text = HexColor("#b91c1c")
            elif "Expert" in diff:
                badge_bg = HexColor("#ede9fe")
                badge_border = HexColor("#c4b5fd")
                badge_text = HexColor("#6d28d9")
            else:
                badge_bg = HexColor("#fef3c7")
                badge_border = HexColor("#fde68a")
                badge_text = HexColor("#b45309")

            card_content = [
                [
                    Paragraph(f"<b>Idea #{itm['id']}: {itm['title']}</b>", styles["IdeaTitle"]),
                    Paragraph(f"<font color='{badge_text}'><b>{itm['difficulty'].upper()}</b></font> &nbsp;|&nbsp; <font color='#475569'>{itm['est_time']}</font>", styles["TableCellCenter"])
                ],
                [
                    Paragraph(f"<b>The Real-World Crisis Problem:</b> {itm['problem']}", styles["IdeaBody"]),
                    ""
                ],
                [
                    Paragraph(f"<b>The Core Innovation & Novelty:</b> {itm['concept']}", styles["IdeaBody"]),
                    ""
                ],
                [
                    Paragraph(f"<b>Architecture & Engine Integration:</b> {itm['architecture']}", styles["IdeaBody"]),
                    ""
                ],
                [
                    Paragraph(f"<b>Recommended Tech Stack & Models:</b> {itm['tech_stack']}", styles["IdeaBody"]),
                    ""
                ],
            ]

            card_table = Table(card_content, colWidths=[412, 120])
            card_table.setStyle(TableStyle([
                ('SPAN', (0, 1), (1, 1)),
                ('SPAN', (0, 2), (1, 2)),
                ('SPAN', (0, 3), (1, 3)),
                ('SPAN', (0, 4), (1, 4)),
                ('BACKGROUND', (0, 0), (-1, -1), HexColor("#ffffff")),
                ('BOX', (0, 0), (-1, -1), 0.75, HexColor("#e2e8f0")),
                ('LINEBELOW', (0, 0), (-1, 0), 0.75, HexColor("#f1f5f9")),
                ('BACKGROUND', (1, 0), (1, 0), badge_bg),
                ('BOX', (1, 0), (1, 0), 0.5, badge_border),
                ('TOPPADDING', (0, 0), (-1, -1), 4),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
                ('LEFTPADDING', (0, 0), (-1, -1), 8),
                ('RIGHTPADDING', (0, 0), (-1, -1), 8),
            ]))

            story.append(KeepTogether([card_table, Spacer(1, 8)]))

        story.append(Spacer(1, 6))

    # -------------------------------------------------------------
    # STRATEGIC IMPLEMENTATION RECOMMENDATION SUMMARY
    # -------------------------------------------------------------
    story.append(PageBreak())
    story.append(Paragraph("Strategic Implementation Priority Roadmap", styles["SectionHeading"]))
    story.append(Paragraph(
        "To maximize research output, demonstration visual impact, and conference publication potential (IEEE Transactions "
        "on Intelligent Transportation Systems, IEEE Access, or ACM SIGSPATIAL), we recommend sequencing development "
        "into four distinct implementation phases.",
        styles["IdeaBody"]
    ))
    story.append(Spacer(1, 8))

    phases_data = [
        [
            Paragraph("<b>Phase & Focus</b>", styles["TableHeader"]),
            Paragraph("<b>Target Proposals Included</b>", styles["TableHeader"]),
            Paragraph("<b>Estimated Time</b>", styles["TableHeader"]),
            Paragraph("<b>Primary Deliverable / Milestone</b>", styles["TableHeader"]),
        ],
        [
            Paragraph("<b>Phase 1: High-Impact Visual Quick Wins</b>", styles["TableCellBold"]),
            Paragraph("Idea 1 (CV Water Depth), Idea 7 (Intermodal Transfer Hubs), Idea 20 (Shelter Epidemic WASH Model)", styles["TableCell"]),
            Paragraph("5–7 Days", styles["TableCellCenter"]),
            Paragraph("Interactive image depth rulers, dual boat-ambulance polyline transfers, shelter health risk meters.", styles["TableCell"]),
        ],
        [
            Paragraph("<b>Phase 2: Explainability & Decision Support</b>", styles["TableCellBold"]),
            Paragraph("Idea 3 (Counterfactual Recourse), Idea 15 (Economic Damage Curves), Idea 10 (Rooftop Supply Drops)", styles["TableCell"]),
            Paragraph("6–8 Days", styles["TableCellCenter"]),
            Paragraph("Dispatch recourse drawer ('How to expedite?'), real-time INR Crores loss graphs, rooftop supply airdrops.", styles["TableCell"]),
        ],
        [
            Paragraph("<b>Phase 3: Resilient Edge Communications</b>", styles["TableCellBold"]),
            Paragraph("Idea 16 (WebRTC Offline SOS Mesh), Idea 17 (CAP 1.2 XML Feed), Idea 19 (AR/QR Virtual Gauges)", styles["TableCell"]),
            Paragraph("7–9 Days", styles["TableCellCenter"]),
            Paragraph("Fully browser-native DTN epidemic mesh routing; official NDMA SACHET alert feed export.", styles["TableCell"]),
        ],
        [
            Paragraph("<b>Phase 4: Advanced AI & Physical Surrogates</b>", styles["TableCellBold"]),
            Paragraph("Idea 11 (2D Hydro PINN), Idea 22 (Adversarial Red-Team Monkey), Idea 24 (MARL Staging Swarm)", styles["TableCell"]),
            Paragraph("12–15 Days", styles["TableCellCenter"]),
            Paragraph("Sub-second shallow water neural solver, automated compound catastrophe stress-testing, QMIX cooperative staging.", styles["TableCell"]),
        ],
    ]

    phases_table = Table(phases_data, colWidths=[130, 160, 65, 177])
    phases_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), HexColor("#0f172a")),
        ('GRID', (0, 0), (-1, -1), 0.5, HexColor("#cbd5e1")),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, HexColor("#f8fafc")]),
    ]))
    story.append(phases_table)
    story.append(Spacer(1, 14))

    # Concluding Note
    concl_text = (
        "<b>Conclusion & Research Significance:</b> AquaSentinel's foundational strength lies in its commitment to "
        "authentic open data (OSM, CWC, WorldPop, Sentinel-1) and zero-fabrication decision science. Implementing these "
        "25 top proposals will elevate the system from a best-in-class university capstone project into a world-leading, "
        "transnational emergency operations digital twin ready for municipal adoption and top-tier journal publication."
    )
    story.append(Table([[Paragraph(concl_text, styles["IdeaBody"])]], colWidths=[532], style=[
        ('BACKGROUND', (0, 0), (-1, -1), HexColor("#f8fafc")),
        ('BOX', (0, 0), (-1, -1), 1, HexColor("#cbd5e1")),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('LEFTPADDING', (0, 0), (-1, -1), 10),
        ('RIGHTPADDING', (0, 0), (-1, -1), 10),
    ]))

    doc.build(story, canvasmaker=NumberedCanvas)
    print(f"[SUCCESS] PDF generated successfully at: {os.path.abspath(filename)}")


if __name__ == "__main__":
    out_file = sys.argv[1] if len(sys.argv) > 1 else "AquaSentinel_Top25_Future_Ideas.pdf"
    build_pdf(out_file)
