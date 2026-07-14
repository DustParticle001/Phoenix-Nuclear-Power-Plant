# US EPR — Plant Systems Control Reference

*Source: US EPR FSAR (AREVA NP / NRC DCA), Chapters 5-11, 18. Compiled for custom MCR layout design.*

---

## MAIN — Main Control Room
*Controlled via PICS workstations or SICS hardwired panel*

| System Group | System Name | Abbreviation | Description / Function |
|---|---|---|---|
| **Reactor Core & Reactivity Control** | Control rod drive control system | CRDCS | Rod cluster control assembly insertion/withdrawal, rod position indication via RPMS |
| | Reactor trip system - manual trip | RTS / SICS | Hardwired manual RT initiation from SICS; automatic trip from PS (TELEPERM XS) |
| | Neutron monitoring system | NMS / EIS | Source-range, intermediate-range, power-range ex-core neutron flux monitoring |
| | In-core instrumentation system | ICIS / SPND | 72 self-powered neutron detectors for DNBR/LPD protection and flux mapping |
| | Reactor control, surveillance & limitation | RCSL | Automated rod control, axial offset alarm, turbine run-back, power limitations |
| | Anti-dilution mitigation system | ADM | Prevents inadvertent dilution of boron concentration at power |
| **Reactor Coolant System** | Reactor coolant pumps | RCP (x4) | Start, stop, speed monitoring; seal injection flow; RCP trip on ECCS initiation |
| | Pressurizer level & pressure control | PZR | Heater group selection, spray valve control, continuous level indication |
| | Pressurizer power-operated relief valves | PORV / POSRV | Manual open/close; block valve position; LTOP monitoring |
| | RCS pressure boundary monitoring | RCS P/T | Loop Tc/Th, pressure, subcooling margin, loop flow - trend displays on PICS |
| **Main Steam System** | Main steam isolation valves | MSIV (x4) | Open/close command from PICS and SICS; position indication; auto-closure on SI or MSLB |
| | Main steam safety/relief valves | MSSV / MSRT | Position indication; MSRT remote manual actuation |
| | Turbine bypass system / steam dump | TBS / TBV | Condenser dump valve control; SG pressure relief during load rejection or trip |
| | SG blowdown isolation & processing | SGBS | Blowdown isolation valve control; activity monitoring tie-in to PICS |
| **Feedwater & Steam Generators** | Main feedwater pumps (turbine-driven) | MFPT (x2) | Speed control, trip, auxiliary oil pump; SG level control via PICS/PAS |
| | Main feedwater flow & SG level | FW / SGL | Three-element level control; feedwater flow transmitters; isolation valve status |
| | Feedwater isolation valves | FWIV | Manual and auto close from PICS or SI actuation; position monitoring |
| | Feedwater heater extraction valves | FWH EXT | Extraction steam valves and drains managed via PICS turbine island displays |
| **Emergency Feedwater System** | EFW motor-driven pump (x2) | EFWP-MD | Manual start/stop from MCR; SICS hardwired initiation; flow to all 4 SGs |
| | EFW turbine-driven pump | EFWP-TD | Remote manual steam admission; auto-start on low SG level / SI actuation |
| | EFW flow & isolation valves | EFWIV | Per-SG isolation valve open/close; flow indication; auto-recirculation |
| **Chemical & Volume Control System** | Charging pumps | CVCS-CP (x3) | Start/stop, flow control; normal charging, ECCS mode switching; RCP seal injection |
| | Boration & dilution control | CVCS B/D | Boric acid batching, dilution valve sequence; boron concentration setpoint |
| | Letdown system | CVCS-LD | Letdown orifice selection, holdup tank level, regenerative HX control |
| | Volume control tank | VCT | Level, pressure, N2 blanket; transfer pump control; chemistry tie-ins |
| | Boron concentration measurement | BCMS | Online boron concentration indication from grab-sample unit and inline measurement |
| | Extra borating system initiation & control | EBS | Diverse boration path; manual actuation from SICS; automatically actuated on SAS signal |
| **Safety Injection / ECCS** | SI actuation (manual ESF) | ESFAS / SICS | Manual initiation from SICS pushbuttons; automatic via PS; 4 divisions |
| | Medium-head safety injection pumps | MHSI (x4) | One per division; injection header valve status; automatic ECCS switchover |
| | Low-head safety injection pumps | LHSI (x4) | One per division; long-term recirculation; tie-in with RHR in recirculation mode |
| | Accumulators (passive injection) | ACC (x4) | N2 pressure and water level monitoring; isolation valve position indication |
| | IRWST level monitoring | IRWST | In-containment refuelling water storage tank inventory; gravity feed confirmation |
| **Residual Heat Removal System** | RHR pumps (x4, 1 per division) | RHRS-P | Start/stop; flow rate control; mode switching injection to recirculation |
| | RHR heat exchanger control | RHRS-HX | Bypass valve control for cooldown temperature rate; CCWS flow tie-in |
| | RHR suction & injection valve alignment | RHRS VLV | Manual or auto valve sequence for cold-leg / hot-leg recirculation alignment |
| **Containment Systems** | Containment isolation actuation | CIA / SICS | Phase A/B isolation manual and automatic; position indication of all CIVs |
| | Containment spray system | CSS (x2) | Manual and auto actuation; spray pump start/stop; additive system monitoring |
| | Containment atmosphere monitoring | CAM | H2 concentration, temperature, pressure; post-accident display on PAMS/QDS |
| | Hydrogen monitoring & igniters | HMS / PAR | H2 sensor display; igniter enable/disable (SICS); passive autocatalytic recombiner status |
| | Containment vacuum relief valves | CVR | Monitoring of vacuum relief actuations; auto-reclose confirmation |
| **Turbine-Generator** | Turbine startup, load & trip | TG / EHC | Electrohydraulic control via PICS; turbine run-up curve; automatic load control |
| | Generator excitation & voltage control | AVR | Automatic voltage regulator setpoint; field current monitoring; reactive power control |
| | Main generator breaker & tie | GEN CB | Breaker close/open command; synchronising check; grid power flow indication |
| **Condenser & Condensate** | Main condenser / air extraction | COND / SGAE | Condenser pressure, hotwell level; steam jet air ejector / vacuum pump status |
| | Condensate pumps | CDP (x3) | Start/stop, flow, pressure; automatic recirculation valve control |
| | Condensate polishing system | CPS | Vessel-in-service selection; resin fouling alarms; conductivity / pH monitoring |
| **Component Cooling Water System** | CCWS pumps - status & alignment | CCWS-P | Pump run/standby status; auto-start on CCWS low-pressure signal; flow headers |
| | CCWS isolation valves (safety-related) | CCWS ISO | Manual and ESFAS-initiated isolation of loads; valve position display |
| **Essential Service Water System** | ESWS pumps - start/stop & alignment | ESWS-P (x4) | One per division; manual and auto start; flow indication; CCWS HX supply |
| | ESWS isolation & bypass valves | ESWS VLV | Division alignment valves; crosstie isolation; ultimate heat sink monitoring |
| **AC/DC Electrical Power** | Normal auxiliary transformers / switchyard | NAT / SWY | Grid voltage monitoring; NAT tap changer; breaker status; load-shedding actuation |
| | Class 1E AC switchgear (4 divisions) | EPSS | 6.9kV Bus tie breaker status; load-shedding sequence status; bus voltage/freq indication |
| | Emergency diesel generators | EDG (x4) | Auto-start confirmation; manual start/stop; output breaker; fuel oil level |
| | Class 1E UPS / battery (x4 per div) | EUPS / BAT | Battery voltage, charger status, inverter alarms; auto-transfer indication |
| | Non-Class 1E UPS | NUPS | Status and alarms for PICS/PAS/PACS power supplies |
| | Manual bus transfer (hardwired) | BUS XFR / SICS | SICS-hardwired manual bus transfer pushbuttons for each safeguard bus |
| **HVAC** | MCR emergency habitability - CRACS | CRACS | Mode selection (normal/recirc); positive pressure monitoring; charcoal filter bypass |
| | Nuclear island / safeguard building HVAC | NI HVAC | Supply/exhaust isolation valves; controlled-area negative pressure monitoring |
| | Fuel building HVAC isolation | FB HVAC | Isolation damper close on high radiation; filter train status |
| | Reactor building containment purge | RB HVAC | Containment purge isolation on high activity; atmosphere temperature monitoring |
| **Radiation Monitoring** | Process & effluent radiation monitoring | PERMS / RMS | Main steam, condenser off-gas, gaseous waste, liquid waste, stack release rates |
| | Area radiation monitoring | ARM | Fixed area monitors throughout plant; high-rad alarms to MCR alarm workstation |
| | Airborne radioactivity monitoring | ABAM | Continuous air samplers in occupied areas; iodine/particulate indication |
| | Post-accident monitoring | PAMS / QDS | Qualified Display System - RCS subcooling, SG level, containment P/T, PZR level |
| | Seismic monitoring system | SMS | Free-field and structural accelerograph indication; SSE threshold alarm |
| **Radioactive Waste Management** | Liquid radwaste - tank & transfer | LRS | Tank level/activity indication; transfer pump status; sampling authorization |
| | Gaseous radwaste - storage & vent | GRS | Delay-bed tank pressure/activity; controlled release valve; stack monitor tie-in |
| | Solid radwaste monitoring | SRS | Drum/package inventory and radiation field alarms from radwaste building monitors |
| **Compressed Air & Sampling** | Instrument / service air pressure monitoring | IAS / SAS | Header pressure alarms; automatic switchover to backup N2 or backup compressor |
| | NSS & process sampling status | NSSS sampling | Sample isolation valve control; radioactive sample routing to MCR display |
| **Spent Fuel & Fuel Handling** | SFP cooling system monitoring | SFPCS | Pool temperature, level; pump run status; makeup alignment via CCWS |
| **Fire Protection** | Fire detection & alarm annunciation | FDS | Zone-by-zone fire alarm display; smoke/heat detector status on MCR annunciator |
| | Fire suppression actuation (key-op) | FSS | Key-operated MCR initiating stations for CO2/FM200 systems in critical rooms |

---

## AUX — Local / Auxiliary Control Stations
*Operated at local panels or LCS outside the MCR*

| System Group | System Name | Abbreviation | Description / Function |
|---|---|---|---|
| **Reactor Core & Reactivity Control** | CRDM local wiring / connectors | CRDM local | Local conduit and connector boxes on reactor head; field access during outages only |
| **Reactor Coolant System** | RCP motor control centres | RCP MCC | Local motor starters and overload protection panels in electrical equipment rooms |
| | Pressurizer heater local panels | PZR HTR | Local breaker panels for backup heater groups in the nuclear auxiliary building |
| **Main Steam System** | MSIV local position indicators | MSIV local | Local position indicators on valve body in main steam tunnel for walkdowns |
| | Steam line drain valves | MSDR local | Warm-up drain valve manual handwheels in steam tunnel; locally operated during startup |
| **Feedwater & Steam Generators** | MFPT local control panel | MFPT local | Local lube-oil, turning-gear and trip-reset panel on feedwater pump deck |
| | Feedwater heater drain local controls | FWH local | Local handvalves and bypass connections on feedwater heater strings |
| **Emergency Feedwater System** | EFW turbine local panel | EFWP-TD local | Local governor and hand-trip on pump turbine; backup hand-valve for steam supply |
| | EFW motor pump local MCCs | EFWP-MD local | Local disconnect and overload panels in safeguard building electrical rooms |
| **Chemical & Volume Control System** | CVCS local panel (charging pump area) | CVCS local | Local valve stations and sample connections near charging pumps in auxiliary building |
| | RCP seal system local | RCP SEAL local | Local pressure and temperature gauges on RCP seal injection/return lines |
| | Extra borating system local panel | EBS local | Local pump/valve panel near IRWST/boron tanks in safeguard buildings |
| **Safety Injection / ECCS** | SI pump local MCCs | SI MCC | Local motor control centres for MHSI/LHSI in safeguard building electrical rooms |
| | Accumulator local isolation valves | ACC ISO local | Local bypass and test valves on accumulator lines; maintenance isolation points |
| **Residual Heat Removal System** | RHR local valve panels | RHRS local | Local handstations on major RHR isolation and throttle valves in safeguard buildings |
| **Containment Systems** | Containment spray pump local panels | CSS local | Local pump start/stop and discharge valve panels in safeguard pump buildings |
| | H2 recombiner local panels | PAR local | Local connection boxes for PAR modules distributed inside containment |
| | CIV local handstations | CIV local | Local (fail-safe) handstations on containment isolation valves for maintenance testing |
| **Turbine-Generator** | Turbine local control panel | TG local | Local EHC workstation on turbine deck; manual turning gear, trip reset, lube oil |
| | Turbine lube oil system | LOS local | Local oil pump start/stop, bearing temp panels on turbine deck |
| | Generator H2 cooling & sealing | GEN H2 local | Local H2 pressure and purity panels beside generator stator |
| | Turning gear local | TG turning gear | Local engage/disengage and speed indication panel at turbine coupling end |
| **Condenser & Condensate** | Circulating water system | CWS local | Local pump start/stop and sluice gate panels at intake structure and cooling tower |
| | Cooling tower fans & basin | CT local | Local fan cell start/stop, basin level, anti-freeze heater controls at cooling tower |
| | Condenser vacuum pump local | COND local | Local start/stop for vacuum priming pumps below turbine deck |
| | Condensate polisher local | CPS local | Local regeneration and resin-transfer control panel in condensate polisher building |
| **Component Cooling Water System** | CCWS local pump MCCs | CCWS local | Local motor control centres in safeguard/nuclear auxiliary buildings |
| | CCWS HX flow control local | CCWS HX local | Local temperature control valves and bypass handvalves at each CCWS HX |
| **Essential Service Water System** | ESWS pump local panels | ESWS local | Local pump houses at UHS/cooling pond; local start and flow gauges |
| | Trash rack / screen wash | ESWS screen | Local screen-wash motors and traveling screen controls at intake structure |
| **AC/DC Electrical Power** | MV/LV switchgear local panels | SWGR local | Local close/open and protection relay panels in electrical equipment rooms |
| | EDG local control panels | EDG local | Local start/stop, governor, voltage regulator panels in diesel generator buildings |
| | Battery charger local panels | BAT local | Local float/equalize selection and ammeter panels in battery rooms |
| | DC distribution local panels | DC local | Local 125 VDC / 24 VDC distribution boards in safeguard building electrical rooms |
| **HVAC** | AHU / fan local control panels | AHU local | Local start/stop and damper handstations on individual air handling units |
| | Chiller / DX unit local controls | CHILLER local | Local compressor and refrigerant panels for each chilled-water unit |
| | Filtered exhaust unit local | FEU local | Local fan start/stop and pressure differential panels on HEPA/charcoal filter trains |
| **Radiation Monitoring** | Local radiation monitors (area-specific) | RM local | Wall-mounted analog/digital readout panels in radiation-controlled areas |
| **Radioactive Waste Management** | Liquid waste processing - local | LWP local | Local evaporator, ion-exchanger and filter panel in radwaste processing building |
| | Gas processing unit local | GPU local | Local compressor, charcoal delay bed and HEPA train controls in radwaste building |
| | Solid waste packaging local | SWP local | Local crane, press and drum filler controls in radwaste packaging area |
| **Compressed Air & Sampling** | Compressor local panels | COMP local | Local start/stop and load/unload controls at each air compressor |
| | Dryer & filter local | CAS local | Local dew-point indication and regeneration-cycle panels at air drying units |
| | Sample panel (chemistry lab area) | SAMP local | Local sample sink, grab-sample valves and flow meters near chemical laboratory |
| **Spent Fuel & Fuel Handling** | SFP makeup & purification | SFPCS local | Local pump and valve panels for SFP cooling loop in fuel building |
| | Fuel handling machine | FHM local | Local operator console on fuel handling machine bridge in fuel/reactor building |
| | Cask decontamination & pit local | CASK local | Local cask pit crane controls and dose-rate meters in spent fuel cask loading area |
| **Fire Protection** | Fire suppression local panels | FSS local | Local fire control panels in each building (nuclear island, turbine, radwaste, etc.) |
| | Diesel fire pump local | DFP local | Local auto-start and manual control panel at diesel-driven fire water pump house |