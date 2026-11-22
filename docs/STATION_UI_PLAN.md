# FieldStation42 Station Configuration UI - Implementation Plan

## Overview

I'm building a web-based UI for managing FieldStation42 station configurations. Currently, users must hand-edit JSON files in the `confs/` directory, which works but has limitations: no real-time validation, easy to make syntax errors, hard to visualize schedules, and you need to understand the complete schema before making changes.

The new UI will provide a browser-based interface for viewing, creating, editing, and managing station configs. I'm taking an **iterative approach** - shipping useful functionality quickly, then progressively layering on convenience features. Each phase adds capability without breaking what came before.

## Design Philosophy

**Raw JSON First, UI Helpers Later**

Instead of starting with complex forms and visual editors, Phase 1 gives you a powerful JSON editor in the browser. This approach has several advantages:

- **Ships faster** - Simple architecture means working software in days, not weeks
- **Full power immediately** - You can edit anything the config format supports, no limitations
- **Validates the foundation** - Gets API endpoints, validation, and error handling solid early
- **Always available** - Even in later phases, raw JSON access remains for advanced features

**Progressive Enhancement**

Each phase builds on previous work:
- Phase 1: Edit existing configs (JSON)
- Phase 2: Create new configs from templates (still JSON, just pre-filled)
- Phase 3: Form-based editing for common properties (with JSON toggle)
- Phase 4: Visual schedule editor (with JSON toggle)

If you're a power user who prefers JSON, you can stop at Phase 1 and be happy. If you want convenience features for common tasks, Phases 3-4 provide that while preserving JSON access for edge cases.

## Phase 1: JSON Editor Foundation

**Goal:** Web-based config management with full feature parity to hand-editing files.

**What you get:**
- **Dashboard** showing all your stations (channel number, name, type)
- **JSON Editor** powered by Monaco (the same editor component VSCode uses)
  - Syntax highlighting for JSON
  - Line numbers, bracket matching
  - Format on paste/type
  - Find/replace, undo/redo
- **Client-side validation** using JSON Schema before save
  - Catches missing required fields
  - Validates data types and formats
  - Shows errors inline with line highlights
- **Server-side validation** as final check
  - Duplicate channel detection
  - Schema enforcement
  - Clear error messages
- **Dirty state tracking** warns you before navigating away with unsaved changes
- **Success/error notifications** so you know what happened

**Technical Details:**
- Monaco Editor loaded from CDN (no build step needed)
- Ajv library for JSON Schema validation
- Integrates with existing FastAPI `/stations` API endpoints
- Uses existing PureCSS styling and theme system
- Vanilla JavaScript - matches rest of FieldStation42 codebase

**User Flow:**
1. Navigate to Station Manager dashboard
2. See list of all stations
3. Click "Edit Config" on any station
4. JSON editor opens with station's current config
5. Edit the JSON directly (add properties, change values, etc.)
6. Click Save - validation runs
7. If valid: saves to API, updates `confs/` file, shows success message
8. If invalid: shows errors with line highlights and explanations

**What Phase 1 doesn't include:**
- Creating new stations (Phase 2)
- Templates (Phase 2)
- Form-based editing (Phase 3)
- Visual schedule grid (Phase 4)

But you can still do all these things by editing JSON - you just type them out manually.

## Phase 2: Template-Based Creation

**Goal:** Make it easy to create new stations without starting from scratch.

**What you get:**
- **"Create New Station" button** on dashboard
- **Template selector** modal with options for each network type:
  - Standard (traditional scheduled TV)
  - Web (embedded web page)
  - Guide (EPG/info channel)
  - Loop (continuous playlist)
  - Streaming (external feeds)
- **Pre-filled JSON** loaded into the editor from template
- **Smart defaults** like suggesting next available channel number
- **Duplicate station** feature (loads existing config as starting point)
- **Delete station** feature (with confirmation)

**Technical Details:**
- Templates stored as static `.json` files in `static/templates/`
- Load via standard fetch, no API changes needed
- Users can add custom templates by dropping files in directory

**User Flow:**
1. Click "Create New Station"
2. Select template type
3. JSON editor opens with template pre-loaded
4. Edit the template (change name, channel, paths, etc.)
5. Save - creates new station

You're still editing JSON at this stage, but you start from a working example instead of an empty file.

## Phase 3: Form-Based Property Editor

**Goal:** Make common property edits faster and more convenient.

**What you get:**
- **View toggle** between Form and JSON modes
- **Tabbed form interface:**
  - **Basic Info:** Network name, channel number, type, scheduling settings
  - **Content & Paths:** Directories, media files, catalog/schedule paths
  - **Playback:** Video settings, display options, logo/OSD configuration
  - **Advanced:** Autobump, clip shows, fallback tags, streaming URLs
- **Form ↔ JSON sync** - changes in forms update the JSON in real-time
- **Type-specific fields** - only show relevant options for each network type
- **Field validation** on individual inputs

**Key Design Decision:**
Forms only handle the most common properties. Advanced features (marathons, sequences, slot overrides, complex schedule features) are still edited via JSON. This keeps forms simple and maintainable while preserving full power.

**User Flow:**
1. Open station editor
2. Toggle to "Form" view
3. Edit properties using labeled fields and dropdowns
4. Switch to "JSON" view anytime to see the underlying config
5. Save from either view

Form view is **optional** - you can keep using JSON if you prefer.

## Phase 4: Visual Schedule Editor

**Goal:** Make schedule editing intuitive for standard networks.

**What you get:**
- **View toggle** between Form, Schedule, and JSON modes
- **Day-by-day schedule table** (24 hours per day)
- **Slot configuration modal** for editing individual time slots
  - Tags (single or multiple)
  - Random tag selection
  - Advanced options (marathons, sequences, effects) - expandable
- **Visual indicators** show which slots have advanced features active
- **Copy day** to other days
- **Day navigation** (previous/next buttons)
- **Schedule ↔ JSON sync** - schedule edits update JSON structure

**User Flow:**
1. Open station editor for standard network
2. Toggle to "Schedule" view
3. Select day from dropdown
4. Click "Edit" on any hour slot
5. Modal opens - configure tags and options
6. Click Apply - table updates
7. Navigate to other days or toggle to JSON to see full config
8. Save from any view

**Scope:**
- Focused on common scheduling tasks (tags, basic marathons, simple sequences)
- Very advanced features (complex slot overrides, nested templates) still easier in JSON
- Schedule view only appears for standard networks (not web, guide, loop, streaming)

Again, schedule view is **optional** - JSON editing remains available for complex configurations.

## Timeline & Priorities

**Phase 1 is the priority.** Once it's working, you have full config management through the web. Everything after that is convenience, not capability.

I'll likely spend time between phases gathering feedback and refining before moving to the next phase. Each phase should be production-ready on its own - this isn't a "wait for v4 to ship" situation.

## Technical Stack

**Frontend:**
- Vanilla JavaScript (no framework, no build step)
- PureCSS 3.0 (already used throughout FieldStation42)
- Monaco Editor (VSCode editor component, CDN-hosted)
- Ajv (JSON Schema validator, CDN-hosted)
- Existing theme system (`themes/default.css`)

**Backend:**
- Existing FastAPI `/stations` API endpoints
- No backend changes needed for Phase 1
- Server-side validation already implemented

**Deployment:**
- Static HTML/CSS/JS files in `fs42/fs42_server/static/`
- Served by FastAPI static file handler
- Integrates with existing web interface

**Why this stack?**
- Matches existing FieldStation42 architecture
- No build tools = simple deployment
- CDN dependencies = no npm/bundling needed
- Small, focused, maintainable

## Why This Approach?

**Why start with raw JSON instead of forms?**

Because forms are limiting. The station config schema is complex and supports a lot of advanced features. Building forms that handle everything would take months and result in a cluttered, confusing UI. Starting with JSON gives you full power immediately while I figure out which properties are actually edited frequently (those become form fields in Phase 3).

**Why not build it all at once?**

Because shipping working software is better than planning perfect software. Phase 1 solves the core problem (editing configs without SSH/terminal access) in a couple weeks. If I tried to build Phases 1-4 simultaneously, you'd wait months for anything usable. Iterative development means you get value early and I can adjust based on real usage patterns.

**Will JSON editing always be available?**

Yes. Some features are genuinely easier to configure as JSON (complex schedules, slot overrides with multiple properties, day templates). Forms can't cover every edge case without becoming overwhelming. Having raw JSON access means power users aren't limited by what the UI happens to support.

## Feedback Welcome

This is the plan, but it's not set in stone. If you have thoughts on the phasing, priorities, or approach, let me know. Especially interested in:
- What would you use most in Phase 1?
- Which Phase 2-4 features matter most to you?
- Are there workflow patterns I'm missing?

Looking forward to getting this built and in your hands.
