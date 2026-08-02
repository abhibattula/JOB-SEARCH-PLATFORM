"""Pure field-taxonomy classifier for Apply Assist (feature 005).

Operates on plain-dict field descriptors serialized from the DOM by
engine/autofill/browser_controller.py — never on live Playwright handles —
so this module stays fully unit-testable with literal fixtures and has no
browser/HTTP imports (Constitution IV: Reusable Core).

Legally-sensitive categories (work_authorization, sponsorship_requirement,
eeo_disclosure) are matched before any generic catch-all, per spec FR-012 —
this taxonomy is intentionally open/extensible, not a fixed two-item list.
login_email/login_password require corroborating context beyond a bare
field type, so a saved credential is never routed into an unrelated field
(research.md §6).
"""
from __future__ import annotations

import re
from typing import Any

FieldDescriptor = dict[str, Any]

# Deliberately excludes <button> and input[type=submit|button|reset] — the
# fill engine has nothing to click, so it collects nothing clickable in the
# first place (first layer of the never-clicks invariant; the second is
# that no fill path contains a click call). Lives here (pure module) so
# every serializer shares one definition.
FIELD_QUERY_SELECTOR = (
    "input:not([type=submit]):not([type=button]):not([type=reset]),"
    " textarea, select,"
    # 011: custom dropdowns that are not native <select> — React-Select and
    # ARIA comboboxes/listboxes (Workday, Greenhouse's newer widgets, etc.)
    " [role=combobox], [role=listbox], [aria-haspopup=listbox],"
    " [class*=select__control],"
    # 020 (FR-016): rich-text editors — the shape a modern cover-letter box
    # takes. Until now these matched nothing, so the field was not merely
    # unfilled, it was never seen. contenteditable=false is display, not
    # input, and is filtered out by the serializers.
    ' [contenteditable=""], [contenteditable="true"], [role=textbox]'
)

_WORK_AUTH_RE = re.compile(
    r"authoriz(e|ation)\w*\s.{0,30}work|legally\s.{0,20}work|work\s.{0,20}(authorization|permit)",
    re.IGNORECASE,
)
_SPONSORSHIP_RE = re.compile(r"sponsor(ship)?", re.IGNORECASE)
_EEO_RE = re.compile(
    r"disabilit\w*|veteran|race\b|ethnicit\w*|gender\s*identity|\beeo\b|equal\s*employment",
    re.IGNORECASE,
)
# 017 (R15, D1): voluntary self-identification gets REAL producer tags, so it
# can be answered from what the applicant stored instead of being refused
# wholesale. Two live defects also required the split: a bare "Gender" label
# never matched _EEO_RE (which demands "gender identity") and therefore
# reached the drafter, and criminal_history/references sat on the denylist
# with no producer at all. Answered from stored values ONLY — never
# generated, never inferred from a name, pronouns, or a resume.
_SELFID_GENDER_RE = re.compile(r"\bgender\b|\bsex\b(?!ual)", re.IGNORECASE)
_SELFID_RACE_RE = re.compile(
    r"\brace\b|\bracial\b|ethnicit\w*|\bethnic\b", re.IGNORECASE)
_SELFID_VETERAN_RE = re.compile(
    r"\bveteran\b|armed\s+forces|\bmilitary\s+service\b", re.IGNORECASE)
_SELFID_DISABILITY_RE = re.compile(
    r"disabilit\w*|chronic\s+condition", re.IGNORECASE)
_SELFID_ORIENTATION_RE = re.compile(
    r"sexual\s+orientation|\btransgender\b|\blgbt", re.IGNORECASE)
_PRONOUNS_RE = re.compile(r"\bpronouns?\b", re.IGNORECASE)
# 009 (FR-005): word separators are [\s_-]* — real ATS markup carries raw
# attributes like first_name / first-name / firstname, which plain \s*
# never matched (root cause A7: fills silently depended on visible labels).
_YEARS_EXPERIENCE_RE = re.compile(
    r"years?[\s_-].{0,15}experience|experience[\s_-].{0,15}years?", re.IGNORECASE
)
_SALARY_RE = re.compile(r"salary|compensation|pay[\s_-].{0,10}expect", re.IGNORECASE)
_HOW_HEARD_RE = re.compile(
    r"how[\s_-].{0,15}hear|referral[\s_-]*source|how[\s_-]did[\s_-]you[\s_-]find",
    re.IGNORECASE,
)
# 011: Workday-style typeahead fields — factual, answer-bank-driven (never
# AI-drafted). "city"/"location" and "school"/"university".
_LOCATION_CITY_RE = re.compile(
    r"\bcity\b|current[\s_-]*location|where[\s_-].{0,20}(located|live)|"
    r"\blocation\b(?!.*preferen)",
    re.IGNORECASE,
)
# 017 (C18, FR-021): the rest of an address. Only `city` existed, so
# "Country*" was left blank on the live Akuna run and Greenhouse's location
# field was mapped to free_text_unknown — the model was asked to guess where
# the applicant lives.
_LOCATION_COUNTRY_RE = re.compile(r"\bcountry\b", re.IGNORECASE)
_LOCATION_STATE_RE = re.compile(
    r"\bstate\b|\bprovince\b|\bregion\b(?!.*preferen)", re.IGNORECASE)
_LOCATION_POSTAL_RE = re.compile(
    r"\bzip\b|\bzip[\s_-]*code\b|\bpostal[\s_-]*code\b|\bpostcode\b",
    re.IGNORECASE)
_LOCATION_ADDRESS2_RE = re.compile(
    r"address[\s_-]*(line[\s_-]*)?2|\bapt\b|\bsuite\b|\bunit\b",
    re.IGNORECASE)
_LOCATION_ADDRESS1_RE = re.compile(
    r"street[\s_-]*address|address[\s_-]*(line[\s_-]*)?1|^address$|"
    r"\bmailing[\s_-]*address\b",
    re.IGNORECASE)

# 017 (FR-022): common application questions the applicant answers once.
_AGE_18_RE = re.compile(
    r"\b18\s+years?\s+(or\s+older|of\s+age)\b|\bat\s+least\s+18\b|"
    r"\bare\s+you\s+18\b",
    re.IGNORECASE)
_NON_COMPETE_RE = re.compile(r"non[\s_-]*compete", re.IGNORECASE)
_CLEARANCE_RE = re.compile(r"security\s+clearance|\bclearance\b", re.IGNORECASE)
_BACKGROUND_CHECK_RE = re.compile(r"background\s+check", re.IGNORECASE)
_DRUG_TEST_RE = re.compile(r"drug\s+(test|screen)", re.IGNORECASE)
_RELOCATE_RE = re.compile(r"\brelocat", re.IGNORECASE)
_TRAVEL_RE = re.compile(r"\bwilling\s+to\s+travel\b|\btravel\s+requirement",
                        re.IGNORECASE)
_START_DATE_RE = re.compile(
    r"start[\s_-]*date|earliest[\s_-].{0,15}start|when\s+can\s+you\s+start|"
    r"available[\s_-].{0,15}start",
    re.IGNORECASE)
_NOTICE_PERIOD_RE = re.compile(r"notice[\s_-]*period", re.IGNORECASE)
_GPA_RE = re.compile(r"\bgpa\b|grade[\s_-]*point", re.IGNORECASE)
_DEGREE_RE = re.compile(
    r"education\s+level|degree\s+(level|type)|highest\s+(level\s+of\s+)?"
    r"education|level\s+of\s+education|are\s+you\s+currently\s+pursuing",
    re.IGNORECASE)
_GRADUATION_RE = re.compile(
    r"graduation\s+(month|year|date)|expected\s+graduation|"
    r"when\s+.{0,20}\bgraduate\b",
    re.IGNORECASE)

# 017 (R16, D5): consent and acknowledgement questions.
_ACKNOWLEDGEMENT_RE = re.compile(
    r"\bi\s+acknowledge\b|\bi\s+certify\b|\bi\s+agree\b|\bi\s+consent\b|"
    r"\bby\s+submitting\b|\bi\s+understand\s+that\b|\bi\s+confirm\b",
    re.IGNORECASE)
# Binding = the applicant GIVES SOMETHING UP. Answering the Akuna exclusivity
# acknowledgement "yes" withdraws them from every other Tech/Quant role at the
# firm for the season, so no automatic path may answer it.
_BINDING_ACK_RE = re.compile(
    r"top\s+preference|will\s+not\s+be\s+considered|sole\s+application|"
    r"not\s+be\s+considered\s+for\s+other|only\s+application|"
    r"non[\s_-]*compete|withdraw\s+.{0,30}other\s+application",
    re.IGNORECASE)


def is_binding_acknowledgement(text: str | None) -> bool:
    """D5: True when agreeing costs the applicant something they cannot get
    back. Binding acknowledgements are never answered automatically — not by
    the model, and not from the answer library."""
    return bool(_BINDING_ACK_RE.search(text or ""))


_SCHOOL_RE = re.compile(
    r"\bschool\b|\buniversity\b|\bcollege\b|\binstitution\b|alma[\s_-]*mater",
    re.IGNORECASE,
)
_LINKEDIN_RE = re.compile(r"linkedin", re.IGNORECASE)
_PORTFOLIO_RE = re.compile(
    r"portfolio|github|personal[\s_-]*website|website[\s_-]*url", re.IGNORECASE
)
# 017 (R6, FR-008): questions about the applicant's OWN HISTORY. A resume
# cannot answer any of these, and every one of them was fabricated on the
# 2026-07-28 live run ("Yes, I have applied to a full-time position with
# Akuna in the past", "Yes, I completed the Options 101 Course", "Yes, I have
# an offer deadline of December 31, 2025", "California"). They get real tags
# so they can be answered from the applicant's own library — never generated.
_APPLIED_BEFORE_RE = re.compile(
    r"\bapplied\b.{0,60}\b(previous\w*|before|in\s+the\s+past)\b|"
    r"\bhave\s+you\s+(ever\s+)?applied\b",
    re.IGNORECASE,
)
_WORKED_HERE_RE = re.compile(
    r"\bworked\s+(for|at|with)\s+(us|our|this\s+company)\b|"
    r"\bformer\s+employee\b|"
    r"\bpreviously\s+employed\s+(by|at|with)\s+(us|our|this)\b",
    re.IGNORECASE,
)
_PRIOR_INDUSTRY_RE = re.compile(
    r"\bprior\s+experience\b|\bprevious\s+experience\s+(at|with|in)\b",
    re.IGNORECASE,
)
_COMPLETED_COURSE_RE = re.compile(
    r"\b(did|have)\s+you\s+completed?\b|"
    r"\bcompleted\s+(our|the)\b.{0,40}\bcourse\b",
    re.IGNORECASE,
)
_OFFER_DEADLINE_RE = re.compile(
    r"\boffer\s+deadlines?\b|\bupcoming\s+deadlines?\b|"
    r"\bdeadlines?\s+that\s+we\s+should\b",
    re.IGNORECASE,
)
_RESIDENCY_RE = re.compile(
    r"\bdo\s+you\s+(currently\s+)?live\s+in\b|"
    r"\bare\s+you\s+a\s+resident\s+of\b|"
    r"\bwhich\s+state\s+do\s+you\s+(live|reside)\b",
    re.IGNORECASE,
)
_CURRENTLY_EMPLOYED_RE = re.compile(r"\bcurrently\s+employed\b", re.IGNORECASE)
_CRIMINAL_RE = re.compile(
    r"\bconvicted\b|\bfelony\b|\bmisdemeanou?r\b|"
    r"\bcriminal\s+(record|history|conviction|background)\b",
    re.IGNORECASE,
)
_REFERENCES_RE = re.compile(
    r"\bprofessional\s+references\b|\bprovide\b.{0,25}\breferences\b|"
    r"\blist\b.{0,25}\breferences\b|\breference\s+contacts?\b",
    re.IGNORECASE,
)

# 017: the classified questions that must never be AI-answered. Kept here
# beside the patterns that produce them so the two cannot drift; the drafter
# imports it as its refusal set.
# 017 (FR-022): questions the applicant answers ONCE in their library. The
# model can no more know whether they hold a clearance than whether they
# applied here before, so these are never generated either — they resolve
# from the answer bank or go to the applicant.
LIBRARY_TAGS = frozenset({
    "age_18_plus", "non_compete", "security_clearance", "background_check",
    "drug_test", "acknowledgement",
})

FACTUAL_HISTORY_TAGS = frozenset({
    "applied_before", "worked_here_before", "prior_industry_experience",
    "completed_course", "offer_deadlines", "residency_state",
    "currently_employed", "criminal_history", "references",
    # a referrer's or reference's name is someone else's fact
    "third_party_name",
    # only the applicant knows how their own name sounds
    "name_pronunciation",
})

# 017 (C3): word-bounded. Without \b, "how your name is pronounced
# PHONEtically" matched and the live run put the applicant's phone number in
# the name-pronunciation box.
_PHONE_RE = re.compile(r"\bphone\b|\bmobile\b|\btelephone\b|\bcell\b",
                       re.IGNORECASE)
_EMAIL_RE = re.compile(r"\bemail\b", re.IGNORECASE)
# 017 (C4): a name field that belongs to SOMEONE ELSE. _FULL_NAME_RE ends in
# a bare \bname\b, so "If you heard about us through an employee, please list
# their name" received the applicant's own name on the live run. Never
# generated either — the model cannot know a referrer's name.
_THIRD_PARTY_NAME_RE = re.compile(
    r"\b(their|his|her|they)\s+name\b|"
    r"\b(employee|employer|referrer|referral|reference|manager|supervisor|"
    r"colleague|contact|emergency|recruiter|friend|person)('?s)?\s+name\b|"
    r"\bname\s+of\s+(the\s+)?(employee|referrer|reference|manager|contact)\b",
    re.IGNORECASE,
)
# 017: "Preferred Name" used to match \bname\b and receive the legal full name.
_PREFERRED_NAME_RE = re.compile(
    r"preferred[\s_-]*name|nick[\s_-]*name|name\s+you\s+(go\s+by|prefer)|"
    r"what\s+should\s+we\s+call\s+you",
    re.IGNORECASE,
)
_MIDDLE_NAME_RE = re.compile(r"middle[\s_-]*(name|initial)", re.IGNORECASE)
# 017: "please write out how your NAME is pronounced phonetically" is not a
# name field. It contains "your name", so every name rule matched it — on the
# live run it received the applicant's phone number (the phone regex had no
# word boundary), and once that was fixed it received their first name
# instead. Only the applicant knows how their name sounds; it is never
# generated.
_NAME_PRONUNCIATION_RE = re.compile(
    r"pronounc\w*|phonetic\w*|how\s+.{0,20}say", re.IGNORECASE)

_FIRST_NAME_RE = re.compile(r"first[\s_-]*name|given[\s_-]*name", re.IGNORECASE)
_LAST_NAME_RE = re.compile(r"last[\s_-]*name|family[\s_-]*name|surname", re.IGNORECASE)
_FULL_NAME_RE = re.compile(r"full[\s_-]*name|your[\s_-]*name|\bname\b", re.IGNORECASE)
_COVER_LETTER_RE = re.compile(r"cover[\s_-]*letter", re.IGNORECASE)
# 019: many ATS login walls (Workday especially) label the identifier
# "Username" rather than "Email".
_USERNAME_RE = re.compile(r"user[\s_-]*name|user[\s_-]*id|account[\s_-]*name",
                          re.IGNORECASE)
_RESUME_RE = re.compile(r"resume|r[eé]sum[eé]|\bcv\b", re.IGNORECASE)


def _haystack(field: FieldDescriptor) -> str:
    parts = (
        field.get("label_text") or "",
        field.get("placeholder") or "",
        field.get("aria_label") or "",
        field.get("name") or "",
        field.get("id") or "",
    )
    text = " ".join(part for part in parts if part).strip()
    if text:
        return text
    # 019 (T026, FR-013): a FALLBACK only. Workday labels its controls with
    # data-automation-id and often nothing else, leaving the haystack empty
    # and the field unclassifiable. Consulting it last means it can never
    # outvote a real label — `legalNameSection_firstName` beside the label
    # "Last Name" must still be the last name.
    return field.get("automation_id") or ""


def classify(field: FieldDescriptor) -> str:
    """Return one taxonomy tag for a serialized form-field descriptor."""
    field_type = (field.get("type") or "").lower()
    tag = (field.get("tag") or "").lower()
    text = _haystack(field)
    autocomplete = (field.get("autocomplete") or "").lower()
    form_context = field.get("form_context")

    # Login fields: require corroborating context, never just a bare type.
    if field_type == "password":
        # type=password has no other legitimate use on a job application —
        # it is itself the corroborating signal.
        # 019 (T042, FR-021): a password on a REGISTRATION form is an
        # account the applicant is creating, not one they have. It gets a
        # generated value saved to the vault; the human presses Create
        # account. Distinguishing the two is what keeps the vault from
        # being asked for a credential that does not exist yet.
        if form_context == "registration" or autocomplete == "new-password":
            return "signup_password"
        return "login_password"
    # 019 (T042, FR-014/FR-020): `form_context` is finally produced by both
    # serializers and carried by the bridge schema, so these two branches
    # are reachable for the first time — before this, `login_email` was
    # dead code and no username tag existed at all.
    is_email_shaped = field_type == "email" or _EMAIL_RE.search(text)
    if form_context in ("login", "registration"):
        if is_email_shaped and autocomplete in ("username", "email", ""):
            return "login_email"
        if autocomplete == "username" or _USERNAME_RE.search(text):
            return "login_username"

    # Legally-sensitive categories — checked before any generic catch-all.
    if _WORK_AUTH_RE.search(text):
        return "work_authorization"
    if _SPONSORSHIP_RE.search(text):
        return "sponsorship_requirement"
    if _PRONOUNS_RE.search(text):
        return "pronouns"
    if _SELFID_ORIENTATION_RE.search(text):
        return "selfid_orientation"
    if _SELFID_DISABILITY_RE.search(text):
        return "selfid_disability"
    if _SELFID_VETERAN_RE.search(text):
        return "selfid_veteran"
    if _SELFID_RACE_RE.search(text):
        return "selfid_race"
    if _SELFID_GENDER_RE.search(text):
        return "selfid_gender"
    if _EEO_RE.search(text):
        return "eeo_disclosure"

    # File uploads — default to resume unless clearly a cover letter upload.
    if field_type == "file":
        if _COVER_LETTER_RE.search(text) and not _RESUME_RE.search(text):
            return "cover_letter"
        return "resume_upload"

    # 017 (FR-008): the applicant's own history — never AI-answerable.
    # Checked before the generic Q&A tags so they cannot fall through to
    # free_text_unknown, which is what let the model invent them.
    if _APPLIED_BEFORE_RE.search(text):
        return "applied_before"
    if _WORKED_HERE_RE.search(text):
        return "worked_here_before"
    if _PRIOR_INDUSTRY_RE.search(text):
        return "prior_industry_experience"
    if _COMPLETED_COURSE_RE.search(text):
        return "completed_course"
    if _OFFER_DEADLINE_RE.search(text):
        return "offer_deadlines"
    if _RESIDENCY_RE.search(text):
        return "residency_state"
    if _CURRENTLY_EMPLOYED_RE.search(text):
        return "currently_employed"
    if _CRIMINAL_RE.search(text):
        return "criminal_history"
    if _REFERENCES_RE.search(text):
        return "references"

    # 017 (D5): consent. Binding ones are never answered by any automatic
    # path; routine ones resolve from the applicant's own library.
    if _ACKNOWLEDGEMENT_RE.search(text):
        return "acknowledgement"

    # 017 (FR-022): common questions the applicant answers once. Checked
    # before the generic Q&A tags so they stop reaching the drafter.
    if _AGE_18_RE.search(text):
        return "age_18_plus"
    if _NON_COMPETE_RE.search(text):
        return "non_compete"
    if _CLEARANCE_RE.search(text):
        return "security_clearance"
    if _BACKGROUND_CHECK_RE.search(text):
        return "background_check"
    if _DRUG_TEST_RE.search(text):
        return "drug_test"
    if _RELOCATE_RE.search(text):
        return "relocate"
    if _TRAVEL_RE.search(text):
        return "travel"
    if _NOTICE_PERIOD_RE.search(text):
        return "notice_period"
    if _START_DATE_RE.search(text):
        return "start_date"
    if _GPA_RE.search(text):
        return "gpa"
    if _GRADUATION_RE.search(text):
        return "graduation_date"
    if _DEGREE_RE.search(text):
        return "degree"

    # 017 (FR-021): the rest of an address.
    if _LOCATION_COUNTRY_RE.search(text):
        return "location_country"
    if _LOCATION_POSTAL_RE.search(text):
        return "location_postal"
    if _LOCATION_ADDRESS2_RE.search(text):
        return "location_address2"
    if _LOCATION_ADDRESS1_RE.search(text):
        return "location_address1"

    # Q&A-bank style fields.
    if _YEARS_EXPERIENCE_RE.search(text):
        return "years_experience"
    if _SALARY_RE.search(text):
        return "salary_expectation"
    if _HOW_HEARD_RE.search(text):
        return "how_heard"
    if _SCHOOL_RE.search(text):
        return "school"
    if _LOCATION_STATE_RE.search(text):
        return "location_state"
    if _LOCATION_CITY_RE.search(text):
        return "location_city"

    # Links.
    if _LINKEDIN_RE.search(text):
        return "linkedin_url"
    if _PORTFOLIO_RE.search(text):
        return "portfolio_url"

    # Basic identity fields. The HTML autocomplete attribute is the
    # highest-confidence identity signal a form can carry (009 FR-005).
    # 017 (C4): name questions that are NOT about the applicant, and the two
    # name variants a bare \bname\b used to swallow. Checked before every
    # other name rule, including the autocomplete shortcuts.
    if _NAME_PRONUNCIATION_RE.search(text):
        return "name_pronunciation"
    if _THIRD_PARTY_NAME_RE.search(text):
        return "third_party_name"
    if _PREFERRED_NAME_RE.search(text):
        return "preferred_name"
    if _MIDDLE_NAME_RE.search(text):
        return "middle_name"

    if autocomplete == "given-name":
        return "first_name"
    if autocomplete == "family-name":
        return "last_name"
    if autocomplete == "name":
        return "full_name"
    if field_type == "tel" or autocomplete == "tel" or _PHONE_RE.search(text):
        return "phone"
    if is_email_shaped or autocomplete == "email":
        return "email"
    if _FIRST_NAME_RE.search(text):
        return "first_name"
    if _LAST_NAME_RE.search(text):
        return "last_name"
    if _FULL_NAME_RE.search(text):
        return "full_name"

    # 020 (D1): a modern cover-letter box is a rich-text editor (an editable
    # <div>), not a <textarea>. Same question, same answer, different
    # element — so the long-free-text gate admits both.
    if (tag == "textarea" or field_type == "richtext") and \
            _COVER_LETTER_RE.search(text):
        return "cover_letter"

    return "free_text_unknown"


# --- structured-input option matching (007, FR-006) --------------------------

# Minimum rapidfuzz ratio for a fuzzy option match. Deliberately strict:
# a wrong structured answer (especially on an authorization dropdown) is
# worse than an unfilled one, which is merely reported for manual review.
# Exercised from both sides by tests/test_fields.py::TestMatchOption.
OPTION_MATCH_CONFIDENCE = 87


def match_option(answer: str, options: list[str],
                 tag: str | None = None) -> str | None:
    """Pick the option whose text best matches a confirmed answer, or None
    when no option matches confidently (the field is then left untouched
    and reported unfilled — never guessed).

    017 (R14, FR-024): `tag` enables a fourth, CANONICAL pass. The first
    three passes cannot bridge vocabulary — "Male" vs "Man" scores ~57 and
    "Y" vs "Yes" scores 50 — so a stored self-identification never matched a
    form that worded its options differently. The canonical pass compares
    exact canonical forms, so it adds no fuzziness to the passes that decide
    work-authorization dropdowns (FR-025).
    """
    from rapidfuzz import fuzz

    normalized_answer = (answer or "").strip().casefold()
    if not normalized_answer or not options:
        return None

    normalized = [(option, (option or "").strip().casefold()) for option in options]

    for option, text in normalized:
        if text == normalized_answer:
            return option
    # "Yes" -> "Yes, I am authorized": the answer as the option's leading
    # word(s), ending at a word boundary — checked before any fuzzy pass so
    # yes/no pairs can never cross-match.
    for option, text in normalized:
        if text.startswith(normalized_answer):
            rest = text[len(normalized_answer):]
            if rest == "" or not rest[:1].isalnum():
                return option

    best_option, best_score = None, 0.0
    for option, text in normalized:
        score = fuzz.ratio(normalized_answer, text)
        if score > best_score:
            best_option, best_score = option, score
    if best_score >= OPTION_MATCH_CONFIDENCE:
        return best_option

    # 017: canonical pass — map both sides into the tag's vocabulary family
    # and compare exactly. Runs last so it can never override a closer
    # literal match, and only when the tag HAS a family (open-ended and
    # identity questions fall through untouched).
    from . import vocab

    family = vocab.family_for_tag(tag)
    if family:
        wanted = vocab.canonical(family, answer)
        if wanted:
            for option, _text in normalized:
                if vocab.canonical(family, option) == wanted:
                    return option
    return None
