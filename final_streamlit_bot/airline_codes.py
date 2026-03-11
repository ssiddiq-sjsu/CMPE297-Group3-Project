"""
Airline code resolution database.
Maps IATA airline codes to full airline names.
"""

AIRLINE_CODES = {
    # Major US Airlines
    "AA": "American Airlines",
    "DL": "Delta Air Lines",
    "UA": "United Airlines",
    "WN": "Southwest Airlines",
    "B6": "JetBlue Airways",
    "AS": "Alaska Airlines",
    "NK": "Spirit Airlines",
    "F9": "Frontier Airlines",
    "HA": "Hawaiian Airlines",
    "G4": "Allegiant Air",
    "SY": "Sun Country Airlines",
    
    # International Airlines
    "AC": "Air Canada",
    "WS": "WestJet",
    "BA": "British Airways",
    "VS": "Virgin Atlantic",
    "AF": "Air France",
    "KL": "KLM Royal Dutch Airlines",
    "LH": "Lufthansa",
    "LX": "Swiss International Air Lines",
    "OS": "Austrian Airlines",
    "SN": "Brussels Airlines",
    "EY": "Etihad Airways",
    "EK": "Emirates",
    "QR": "Qatar Airways",
    "TK": "Turkish Airlines",
    "SQ": "Singapore Airlines",
    "CX": "Cathay Pacific",
    "JL": "Japan Airlines",
    "NH": "All Nippon Airways",
    "KE": "Korean Air",
    "OZ": "Asiana Airlines",
    "QF": "Qantas",
    "NZ": "Air New Zealand",
    "VA": "Virgin Australia",
    "JJ": "LATAM Brasil",
    "LA": "LATAM Airlines",
    "AV": "Avianca",
    "AM": "Aeromexico",
    "VB": "Viva Aerobus",
    "Y4": "Volaris",
    "CM": "Copa Airlines",
    
    # European Airlines
    "IB": "Iberia",
    "EY": "Etihad Airways",
    "EK": "Emirates",
    "QR": "Qatar Airways",
    "TK": "Turkish Airlines",
    "AZ": "ITA Airways",
    "TP": "TAP Air Portugal",
    "A3": "Aegean Airlines",
    "OU": "Croatia Airlines",
    "LO": "LOT Polish Airlines",
    "OK": "Czech Airlines",
    "JU": "Air Serbia",
    "RO": "Tarom",
    "FB": "Bulgaria Air",
    "BT": "Air Baltic",
    "SK": "SAS Scandinavian Airlines",
    "DY": "Norwegian Air Shuttle",
    "D8": "Norwegian Air International",
    "FI": "Icelandair",
    "WW": "WOW air",
    
    # Asian Airlines
    "CZ": "China Southern Airlines",
    "MU": "China Eastern Airlines",
    "CA": "Air China",
    "HU": "Hainan Airlines",
    "MF": "Xiamen Airlines",
    "3U": "Sichuan Airlines",
    "ZH": "Shenzhen Airlines",
    "SC": "Shandong Airlines",
    "HO": "Juneyao Air",
    "9C": "Spring Airlines",
    "BR": "EVA Air",
    "CI": "China Airlines",
    "PR": "Philippine Airlines",
    "5J": "Cebu Pacific",
    "Z2": "Philippines AirAsia",
    "AK": "AirAsia",
    "D7": "AirAsia X",
    "FD": "Thai AirAsia",
    "SL": "Thai Lion Air",
    "VZ": "Thai Vietjet Air",
    "VJ": "VietJet Air",
    "VN": "Vietnam Airlines",
    "MH": "Malaysia Airlines",
    "OD": "Malindo Air",
    "TR": "Scoot",
    "GA": "Garuda Indonesia",
    "QZ": "Indonesia AirAsia",
    "JT": "Lion Air",
    "ID": "Batik Air",
    "IW": "Wings Air",
    "UL": "SriLankan Airlines",
    "PK": "Pakistan International Airlines",
    "AI": "Air India",
    "6E": "IndiGo",
    "SG": "SpiceJet",
    "G8": "GoAir",
    "UK": "Vistara",
    "9W": "Jet Airways",
    "S2": "JetLite",
    
    # Middle Eastern Airlines
    "WY": "Oman Air",
    "GF": "Gulf Air",
    "KU": "Kuwait Airways",
    "RJ": "Royal Jordanian",
    "ME": "Middle East Airlines",
    "RB": "Syrian Arab Airlines",
    "IA": "Iraqi Airways",
    "IR": "Iran Air",
    "W5": "Mahan Air",
    
    # African Airlines
    "MS": "EgyptAir",
    "AT": "Royal Air Maroc",
    "AH": "Air Algérie",
    "TU": "Tunisair",
    "ET": "Ethiopian Airlines",
    "KQ": "Kenya Airways",
    "SA": "South African Airways",
    "FA": "FlySafair",
    "4Z": "Airlink",
    "MN": "Kulula.com",
    
    # Cargo Airlines
    "FX": "FedEx Express",
    "5X": "UPS Airlines",
    "PO": "Polar Air Cargo",
    "CV": "Cargolux",
    "CK": "China Cargo Airlines",
    "KZ": "ANA Cargo",
    "NH": "ANA Cargo",
    "SQ": "Singapore Airlines Cargo",
    
    # Regional/Commuter Airlines
    "OO": "SkyWest Airlines",
    "QX": "Horizon Air",
    "OH": "PSA Airlines",
    "YX": "Republic Airways",
    "MQ": "Envoy Air",
    "9E": "Endeavor Air",
    "CP": "Compass Airlines",
    "ZW": "Air Wisconsin",
    "PT": "Piedmont Airlines",
    
    # Charter Airlines
    "1T": "Bulgarian Air Charter",
    "HQ": "Thomas Cook Airlines",
    "MT": "Thomas Cook Airlines",
    "BY": "TUI Airways",
    "X3": "TUI fly",
    "TB": "TUI fly Belgium",
    "OR": "TUI fly Netherlands",
    "DE": "Condor",
    "XQ": "SunExpress",
    "EW": "Eurowings",
    "4U": "Germanwings",
    
    # Low Cost Carriers
    "FR": "Ryanair",
    "U2": "easyJet",
    "W6": "Wizz Air",
    "HV": "Transavia",
    "TO": "Transavia France",
    "VY": "Vueling Airlines",
    "DY": "Norwegian Air Shuttle",
    "D8": "Norwegian Air International",
    "WW": "WOW air",
    "W9": "Wizz Air UK",
    "5W": "Wizz Air Abu Dhabi",
    
    # Unknown/Default
    "N/A": "Unknown Airline",
}


def resolve_airline_code(code: str) -> str:
    """
    Resolve an IATA airline code to a full airline name.
    
    Args:
        code: IATA airline code (e.g., "B6", "AA", "UA")
        
    Returns:
        Full airline name or the original code if not found
    """
    if not code or code == "N/A":
        return "Unknown Airline"
    
    # Clean the code (remove any whitespace, convert to uppercase)
    clean_code = code.strip().upper()
    
    # Try direct lookup
    if clean_code in AIRLINE_CODES:
        return AIRLINE_CODES[clean_code]
    
    # If code has numbers attached (e.g., "B6123"), extract just the code part
    import re
    code_match = re.match(r'^([A-Z]{2})', clean_code)
    if code_match:
        base_code = code_match.group(1)
        if base_code in AIRLINE_CODES:
            return AIRLINE_CODES[base_code]
    
    # If it looks like a flight number (e.g., "UA123"), extract airline code
    flight_match = re.match(r'^([A-Z]{2})\d+', clean_code)
    if flight_match:
        airline_code = flight_match.group(1)
        if airline_code in AIRLINE_CODES:
            return AIRLINE_CODES[airline_code]
    
    # Return original if not found
    return code


def get_airline_with_code(code: str) -> str:
    """
    Get airline name with code in parentheses.
    
    Args:
        code: IATA airline code
        
    Returns:
        Formatted string: "Airline Name (CODE)" or just the code if not found
    """
    name = resolve_airline_code(code)
    if name == code:
        return code
    return f"{name} ({code})"


# Common airline code mappings for quick reference
COMMON_AIRLINES = {
    "B6": "JetBlue Airways",
    "AA": "American Airlines",
    "DL": "Delta Air Lines",
    "UA": "United Airlines",
    "WN": "Southwest Airlines",
    "AS": "Alaska Airlines",
    "NK": "Spirit Airlines",
    "F9": "Frontier Airlines",
}