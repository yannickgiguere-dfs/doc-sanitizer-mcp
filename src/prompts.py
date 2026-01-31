"""LLM prompt templates for PII sanitization."""

from .config_schema import Profile, PIIType, PIIAction


def build_sanitization_prompt(document_text: str, profile: Profile) -> str:
    """Build the LLM prompt for document sanitization.

    Args:
        document_text: The extracted document text to sanitize
        profile: The sanitization profile with PII handling rules

    Returns:
        Complete prompt string for the LLM
    """
    rules = _build_rules_section(profile)

    prompt = f"""You are a document sanitization expert. Your task is to process the following document and remove or transform personally identifiable information (PII) according to the specific rules provided.

## CRITICAL INSTRUCTIONS

1. **Preserve Document Structure**: Maintain all headings, tables, lists, and formatting exactly as they appear.
2. **Consistency**: If the same entity (person, company, etc.) appears multiple times, use the SAME replacement throughout the entire document.
3. **Context Awareness**: Use context to identify PII that may not follow standard formats.
4. **Output Format**: Return ONLY the sanitized document content. Do not include explanations or metadata.

## PII HANDLING RULES

{rules}

## ENTITY TRACKING

You MUST track entities to ensure consistency:
- If "John Smith" appears 5 times and the rule is KEEP_PART, all 5 instances must become "John 1"
- If a second person named "John Davis" appears, they become "John 2"
- If the rule is INVENT, invent ONE replacement name and use it for ALL occurrences

## DOCUMENT TO SANITIZE

{document_text}

## OUTPUT

Return the sanitized document below. Preserve all formatting (markdown headers, tables, lists, etc.):
"""

    return prompt


def _build_rules_section(profile: Profile) -> str:
    """Build the rules section of the prompt from profile configuration."""
    rules = []

    config = profile.config

    # Person names
    action = config.person_name.action
    if action == PIIAction.DELETE:
        rules.append("""### Person Names (DELETE)
- Remove ALL person names completely
- Replace with: [NAME_REMOVED]
- Examples:
  - "John Smith sent the email" → "[NAME_REMOVED] sent the email"
  - "Contact Sarah Johnson" → "Contact [NAME_REMOVED]"
""")
    elif action == PIIAction.INVENT:
        rules.append("""### Person Names (INVENT)
- Replace ALL person names with consistent synthetic names
- IMPORTANT: Same original name = same invented name throughout
- Examples:
  - "John Smith" → "Alex Chen" (all occurrences)
  - "Sarah Johnson" → "Maria Garcia" (all occurrences)
- Keep the invented names realistic and professional
""")
    elif action == PIIAction.KEEP_PART:
        rules.append("""### Person Names (KEEP_PART)
- Keep ONLY the first name
- Drop middle names and last names completely
- Number duplicate first names sequentially
- Examples:
  - "John Michael Smith" → "John 1"
  - "John Andrew Davis" (different person) → "John 2"
  - "Sarah Johnson" → "Sarah 1"
- Track which original person maps to which number for consistency
""")

    # Email addresses
    action = config.email.action
    if action == PIIAction.DELETE:
        rules.append("""### Email Addresses (DELETE)
- Remove ALL email addresses completely
- Replace with: [EMAIL_REMOVED]
- Examples:
  - "Contact john.smith@company.com" → "Contact [EMAIL_REMOVED]"
""")
    elif action == PIIAction.KEEP_PART:
        rules.append("""### Email Addresses (KEEP_PART)
- Keep the domain name only
- Remove the local part (before @)
- Format: [EMAIL_REDACTED]@domain.com
- Examples:
  - "john.smith@company.com" → "[EMAIL_REDACTED]@company.com"
  - "ceo@example.org" → "[EMAIL_REDACTED]@example.org"
""")

    # Phone numbers
    action = config.phone.action
    if action == PIIAction.DELETE:
        rules.append("""### Phone Numbers (DELETE)
- Remove ALL phone numbers completely
- Replace with: [PHONE_REMOVED]
- Match all formats: international, local, with/without spaces/dashes
- Examples:
  - "+1 (555) 123-4567" → "[PHONE_REMOVED]"
  - "555.123.4567" → "[PHONE_REMOVED]"
""")
    elif action == PIIAction.INVENT:
        rules.append("""### Phone Numbers (INVENT)
- Replace with synthetic phone numbers
- Maintain the same format and country/area code style
- Examples:
  - "+1 (555) 123-4567" → "+1 (555) 987-6543"
  - "+61 2 1234 5678" → "+61 2 8765 4321"
""")
    elif action == PIIAction.KEEP_PART:
        rules.append("""### Phone Numbers (KEEP_PART)
- Keep country code and area code only
- Remove remaining digits
- Format: +XX (XX) [REDACTED]
- Examples:
  - "+1 (555) 123-4567" → "+1 (555) [REDACTED]"
  - "+61 2 1234 5678" → "+61 (2) [REDACTED]"
""")

    # Company names
    action = config.company.action
    if action == PIIAction.KEEP_PART:
        rules.append("""### Company Names (KEEP_PART)
- Keep company names exactly as-is
- No modification needed
- Distinguish companies from person names using context
""")
    elif action == PIIAction.INVENT:
        rules.append("""### Company Names (INVENT)
- Replace company names with consistent synthetic names
- IMPORTANT: Same original company = same invented name throughout
- Examples:
  - "Acme Corp" → "TechFlow Industries" (all occurrences)
  - "Google" → "DataSphere Inc" (all occurrences)
- Keep invented names realistic and business-appropriate
""")

    # Addresses
    action = config.address.action
    if action == PIIAction.DELETE:
        rules.append("""### Physical Addresses (DELETE)
- Remove ALL physical addresses completely
- Replace with: [ADDRESS_REMOVED]
- Match street addresses, PO boxes, city/state/zip combinations
- Examples:
  - "123 Main St, New York, NY 10001" → "[ADDRESS_REMOVED]"
  - "PO Box 456, Seattle WA" → "[ADDRESS_REMOVED]"
""")
    elif action == PIIAction.INVENT:
        rules.append("""### Physical Addresses (INVENT)
- Replace with synthetic addresses
- Maintain same format and general location type
- Examples:
  - "123 Main St, New York, NY 10001" → "456 Oak Ave, Chicago, IL 60601"
  - Keep consistency if same address appears multiple times
""")

    # Financial data
    action = config.financial.action
    if action == PIIAction.DELETE:
        rules.append("""### Financial Data (DELETE)
- Remove ALL financial data completely
- This includes: account numbers, credit card numbers, bank details, specific monetary amounts tied to individuals
- Replace with: [FINANCIAL_REMOVED]
- Note: General business figures or statistics may be kept unless tied to specific individuals
""")
    elif action == PIIAction.INVENT:
        rules.append("""### Financial Data (INVENT)
- Replace financial data with synthetic values
- Maintain same format (e.g., 16-digit card numbers, account number patterns)
- For amounts, use similar order of magnitude
""")

    # ID numbers
    action = config.id_numbers.action
    if action == PIIAction.DELETE:
        rules.append("""### ID Numbers (DELETE)
- Remove ALL identification numbers completely
- This includes: employee IDs, customer IDs, SSN/TFN, passport numbers, driver's license numbers
- Replace with: [ID_REMOVED]
""")
    elif action == PIIAction.INVENT:
        rules.append("""### ID Numbers (INVENT)
- Replace ID numbers with synthetic values
- Maintain same format and length
- Examples:
  - "EMP-12345" → "EMP-67890"
  - SSN format "123-45-6789" → "987-65-4321"
""")

    # Date of birth
    action = config.date_of_birth.action
    if action == PIIAction.DELETE:
        rules.append("""### Dates of Birth (DELETE)
- Remove ALL dates of birth completely
- Replace with: [DOB_REMOVED]
- Look for context clues like "born on", "DOB:", "birthday", age calculations
""")
    elif action == PIIAction.INVENT:
        rules.append("""### Dates of Birth (INVENT)
- Replace with synthetic dates
- Maintain reasonable age range based on context
- Keep same date format as original
""")

    return "\n".join(rules)


def build_yaml_frontmatter(
    source_type: str,
    model_used: str,
    profile_name: str,
) -> str:
    """Build YAML frontmatter for sanitized document output.

    Args:
        source_type: Type of source document (docx, pdf, etc.)
        model_used: Name of the LLM model used
        profile_name: Name of the sanitization profile used

    Returns:
        YAML frontmatter string
    """
    from datetime import datetime

    timestamp = datetime.utcnow().isoformat() + "Z"

    frontmatter = f"""---
source_type: {source_type}
sanitization_timestamp: {timestamp}
model_used: {model_used}
profile_used: {profile_name}
---

"""
    return frontmatter
