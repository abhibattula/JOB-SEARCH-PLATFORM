"""Generates tests/fixtures/ats_pages/workday_my_experience.html.

021 (T018). The two Workday fixtures this suite already had hold 9 and 2
fields, which is exactly why the failure the applicant hit was never caught:
v2.0.0 met a real Intel Workday application and reported Filled 5 / Needs you
149 / Seen 156, most rows blank.

This fixture reproduces the MECHANISMS proven in research R1 — read out of the
source, not guessed — at the SCALE the applicant reported:

  * one question served by TWO elements (a Workday prompt is a button with
    aria-haspopup=listbox PLUS its listbox, and FIELD_SELECTOR matches both).
    This is the duplicate-row engine.
  * fields whose label resolves to WHITESPACE, so `question_of()` — which has
    no .strip() — creates a row that renders blank.
  * repeated Work Experience and Education blocks, so the same question
    ("Start date", "Overall Result (GPA)") legitimately appears many times and
    must NOT be collapsed into one row.
  * fields whose only identity is data-automation-id, which the scanner
    captures and the panel throws away.

The labels are the ones the applicant could actually read in the flood:
Country/Region*, State, Country/Region Phone Code*, Location,
I currently work here, Overall Result (GPA).

Regenerate with:
    .venv/Scripts/python.exe tests/fixtures/ats_pages/_build_workday_my_experience.py

The generator is committed alongside the HTML so the fixture's structure is
reviewable as intent rather than as 2,000 lines of markup, and so it can be
re-shaped when the applicant's real capture (T012) refines it.
"""
from __future__ import annotations

from pathlib import Path

OUT = Path(__file__).resolve().parent / "workday_my_experience.html"

WORK_BLOCKS = 3
EDU_BLOCKS = 2


def prompt(automation_id: str, label: str, options: list[str]) -> str:
    """A Workday prompt: a button that opens a listbox.

    BOTH elements match FIELD_SELECTOR ([aria-haspopup=listbox] and
    [role=listbox]), so one question arrives as two descriptors. That is the
    duplicate-row mechanism, reproduced exactly.
    """
    option_html = "".join(
        f'<div role="option" data-automation-id="promptOption">{o}</div>'
        for o in options)
    return f"""
      <div class="fieldset-wrap">
        <label id="lbl-{automation_id}">{label}</label>
        <button type="button" aria-haspopup="listbox" aria-expanded="false"
                aria-labelledby="lbl-{automation_id}"
                data-automation-id="{automation_id}">Select One</button>
        <div role="listbox" aria-labelledby="lbl-{automation_id}"
             data-automation-id="{automation_id}Listbox">{option_html}</div>
        <input type="text" name="{automation_id}" data-automation-id="{automation_id}Input">
      </div>"""


def text(automation_id: str, label: str, name: str = "",
         required: bool = False) -> str:
    star = "*" if required else ""
    req = ' aria-required="true"' if required else ""
    return f"""
      <label>{label}{star}<input type="text" name="{name or automation_id}"
             data-automation-id="{automation_id}"{req}></label>"""


def unlabelled(automation_id: str) -> str:
    """A field whose label resolves to WHITESPACE.

    `question_of()` is `label_text or placeholder or aria_label or ""` with no
    .strip(), and " " is truthy in Python — so a row is created and renders
    blank. Its only real identity is the automation id.
    """
    return f"""
      <label> <input type="text" name="{automation_id}"
             data-automation-id="{automation_id}"></label>"""


def checkbox(automation_id: str, label: str) -> str:
    return f"""
      <label><input type="checkbox" name="{automation_id}"
             data-automation-id="{automation_id}">{label}</label>"""


def work_block(index: int) -> str:
    n = index + 1
    return f"""
    <section role="group" aria-label="Work Experience"
             data-automation-id="workExperienceSection">
      <h3>Work Experience {n}</h3>
      {text(f"jobTitle-{n}", "Job Title")}
      {text(f"company-{n}", "Company")}
      {text(f"location-{n}", "Location")}
      {checkbox(f"currentlyWorkHere-{n}", "I currently work here")}
      {text(f"startDate-{n}", "From")}
      {text(f"endDate-{n}", "To")}
      {text(f"roleDescription-{n}", "Role Description")}
      {unlabelled(f"workExtra-{n}")}
    </section>"""


def edu_block(index: int) -> str:
    n = index + 1
    return f"""
    <section role="group" aria-label="Education"
             data-automation-id="educationSection">
      <h3>Education {n}</h3>
      {text(f"school-{n}", "School or University")}
      {prompt(f"degree-{n}", "Degree", ["Bachelor's Degree", "Master's Degree"])}
      {text(f"fieldOfStudy-{n}", "Field of Study")}
      {text(f"gpa-{n}", "Overall Result (GPA)")}
      {text(f"eduFrom-{n}", "From")}
      {text(f"eduTo-{n}", "To")}
      {unlabelled(f"eduExtra-{n}")}
    </section>"""


def skills_rows() -> str:
    """Filler at real Workday density — Skills, Websites and Languages carry
    a long tail of near-identical controls, which is a large part of how a
    single page reaches 150 fields."""
    rows = []
    # "URL" repeated is the other legitimate duplicate: same question, same
    # section, genuinely different fields. Distinguished only by their
    # automation id — which is exactly what question resolution must fall
    # back to, and what the panel currently discards.
    for n in range(1, 17):
        rows.append(text(f"websiteUrl-{n}", "URL"))
    for n in range(1, 13):
        rows.append(prompt(f"language-{n}", "Language",
                           ["English", "Hindi", "Telugu"]))
    for n in range(1, 41):
        rows.append(unlabelled(f"skillChip-{n}"))
    return "".join(rows)


def build() -> str:
    address = "".join([
        text("addressLine1", "Address Line 1", required=True),
        text("addressLine2", "Address Line 2"),
        text("city", "City", required=True),
        prompt("countryRegion", "Country/Region",
               ["United States of America", "India"]),
        prompt("state", "State", ["Texas", "California", "Karnataka"]),
        text("postalCode", "Postal Code", required=True),
    ])
    contact = "".join([
        text("firstName", "First Name", required=True),
        text("lastName", "Last Name", required=True),
        text("email", "Email Address", required=True),
        prompt("phoneCountryCode", "Country/Region Phone Code",
               ["+1", "+91"]),
        text("phoneNumber", "Phone Number", required=True),
        unlabelled("contactExtra"),
    ])
    work = "".join(work_block(i) for i in range(WORK_BLOCKS))
    edu = "".join(edu_block(i) for i in range(EDU_BLOCKS))

    return f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<title>My Experience — Workday</title></head>
<body>
<h1>My Experience</h1>
<form id="form">
  <section role="group" aria-label="Contact Information"
           data-automation-id="contactInformationSection">
    <h2>Contact Information</h2>{contact}
  </section>

  <section role="group" aria-label="Address"
           data-automation-id="addressSection">
    <h2>Address</h2>{address}
  </section>
{work}{edu}
  <section role="group" aria-label="Websites and Skills"
           data-automation-id="websitesSection">
    <h2>Websites and Skills</h2>{skills_rows()}
  </section>

  <!-- Deliberately OUTSIDE every section container: the undetermined case.
       The app must degrade to a flat group here, never guess a section. -->
  <label>Additional Information<textarea name="additionalInfo"
    data-automation-id="additionalInfo"></textarea></label>

  <button type="button" id="wd-next">Save and Continue</button>
</form>
<script src="/_mirror.js"></script>
<script>
  // Workday's prompts open on click. The listbox is present in the DOM
  // either way — which is precisely why one question arrives as two
  // descriptors, and why de-duplicating by ELEMENT produced the flood.
  document.querySelectorAll('[aria-haspopup="listbox"]').forEach(function (b) {{
    var box = b.parentElement.querySelector('[role="listbox"]');
    var mirror = b.parentElement.querySelector('input');
    b.addEventListener('click', function () {{
      b.setAttribute('aria-expanded', 'true');
    }});
    box.querySelectorAll('[role="option"]').forEach(function (o) {{
      o.addEventListener('click', function () {{
        b.textContent = o.textContent;
        if (mirror) {{
          mirror.value = o.textContent;
          mirror.dispatchEvent(new Event('input', {{ bubbles: true }}));
        }}
      }});
    }});
  }});
</script>
</body></html>
"""


if __name__ == "__main__":
    OUT.write_text(build(), encoding="utf-8")
    html = OUT.read_text(encoding="utf-8")
    print(f"wrote {OUT}")
    print(f"  inputs/selects/textareas: "
          f"{html.count('<input') + html.count('<select') + html.count('<textarea')}")
    print(f"  listbox triggers:         {html.count('aria-haspopup=')}")
    print(f"  listboxes:                {html.count('role=\"listbox\"')}")
