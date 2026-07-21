# Executive Summary

**poc-data-extraction** is a working prototype that reads screenshots of a bank's internal software and turns what it sees on screen into organized, checkable data; then grades its own work and reports what it cost.

## The problem it solves

At BPER, an Italian banking group, the details of a credit file (customer names and account numbers, loan amounts, guarantees, income and employment data) live on the screens of an internal application. Moving that information anywhere else currently means a person reading the screen and re-typing everything by hand. That is slow, tedious, and easy to get wrong.

## How it works, in plain terms

You give the software a screenshot of one of those screens, or let it quietly watch the monitor while an operator pages through the application. It sends the picture to an AI service that can look at images and answer questions about them: the same kind of technology behind modern chat assistants. It asks in three careful steps: first *"whose file is this?"* to lock onto the right customer, then *"read everything on this page"*, and finally *"take another look at just the parts you weren't sure about."* Every answer comes back as a labeled entry with a confidence level attached.

Think of it as a diligent clerk paired with a strict supervisor. The clerk transcribes each screen into a form. The supervisor then compares every entry against an answer sheet of known-correct values, marks each one as right, wrong, missed, or invented, and keeps a running tab of exactly what each page cost to read, because the AI services behind this charge per use.

## What you get out of it

- For every screen: a structured data record, around 45 fields, each with a confidence score.
- For every run: an accuracy report (which fields the AI got right, per field and overall) and a cost report (how much money each screen cost to process).

Together these answer the question the project exists to answer: **can AI reliably replace manual re-typing of these banking screens, and at what price?**

## Who it is for

The engineers at Tri-tech solutions who build and evaluate the system. A desktop application is also included that a bank operator could use directly: it watches the screen, recognizes which page is open, and captures the data automatically, suggesting which page to open next.

## Honest status

This is a proof of concept in active development, not a finished product. There are no automated tests, no installer, and results are checked by hand against a reference sheet. It proves and measures an approach; it is not ready to hand to end users as-is.

## Where to go next

- **Non-technical readers:** the [Glossary](11-glossary.md) explains every term used in these documents. An Italian plain-language guide to the whole project also lives in `docs/` (start at `docs/INDEX.md`).
- **Developers:** start with the [Overview](01-overview.md), then [Architecture](04-architecture.md) for how the pieces fit together, and [Getting Started](07-getting-started.md) to run it yourself.
