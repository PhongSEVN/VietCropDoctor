---
name: Agro-Medical Intelligence
colors:
  surface: '#f4fcf0'
  surface-dim: '#d5dcd1'
  surface-bright: '#f4fcf0'
  surface-container-lowest: '#ffffff'
  surface-container-low: '#eff6ea'
  surface-container: '#e9f0e5'
  surface-container-high: '#e3eadf'
  surface-container-highest: '#dde5d9'
  on-surface: '#171d16'
  on-surface-variant: '#3e4a3d'
  inverse-surface: '#2b322b'
  inverse-on-surface: '#ecf3e7'
  outline: '#6e7b6c'
  outline-variant: '#bdcaba'
  surface-tint: '#006e2d'
  primary: '#006b2c'
  on-primary: '#ffffff'
  primary-container: '#00873a'
  on-primary-container: '#f7fff2'
  inverse-primary: '#62df7d'
  secondary: '#904d00'
  on-secondary: '#ffffff'
  secondary-container: '#fe932c'
  on-secondary-container: '#663500'
  tertiary: '#a72d51'
  on-tertiary: '#ffffff'
  tertiary-container: '#c74668'
  on-tertiary-container: '#fffbff'
  error: '#ba1a1a'
  on-error: '#ffffff'
  error-container: '#ffdad6'
  on-error-container: '#93000a'
  primary-fixed: '#7ffc97'
  primary-fixed-dim: '#62df7d'
  on-primary-fixed: '#002109'
  on-primary-fixed-variant: '#005320'
  secondary-fixed: '#ffdcc3'
  secondary-fixed-dim: '#ffb77d'
  on-secondary-fixed: '#2f1500'
  on-secondary-fixed-variant: '#6e3900'
  tertiary-fixed: '#ffd9de'
  tertiary-fixed-dim: '#ffb2bf'
  on-tertiary-fixed: '#3f0016'
  on-tertiary-fixed-variant: '#8a143c'
  background: '#f4fcf0'
  on-background: '#171d16'
  surface-variant: '#dde5d9'
typography:
  display-lg:
    fontFamily: Inter
    fontSize: 48px
    fontWeight: '700'
    lineHeight: 56px
    letterSpacing: -0.02em
  headline-lg:
    fontFamily: Inter
    fontSize: 32px
    fontWeight: '600'
    lineHeight: 40px
    letterSpacing: -0.01em
  headline-lg-mobile:
    fontFamily: Inter
    fontSize: 24px
    fontWeight: '600'
    lineHeight: 32px
  title-md:
    fontFamily: Inter
    fontSize: 20px
    fontWeight: '600'
    lineHeight: 28px
  body-lg:
    fontFamily: Inter
    fontSize: 18px
    fontWeight: '400'
    lineHeight: 28px
  body-md:
    fontFamily: Inter
    fontSize: 16px
    fontWeight: '400'
    lineHeight: 24px
  label-md:
    fontFamily: Inter
    fontSize: 14px
    fontWeight: '500'
    lineHeight: 20px
    letterSpacing: 0.01em
  label-sm:
    fontFamily: Inter
    fontSize: 12px
    fontWeight: '600'
    lineHeight: 16px
    letterSpacing: 0.05em
rounded:
  sm: 0.25rem
  DEFAULT: 0.5rem
  md: 0.75rem
  lg: 1rem
  xl: 1.5rem
  full: 9999px
spacing:
  unit: 8px
  container-padding-mobile: 16px
  container-padding-desktop: 32px
  gutter: 24px
  component-gap: 12px
---

## Brand & Style
The design system focuses on a fusion of agricultural vitality and medical precision. It is engineered to evoke trust, clarity, and urgent utility for farmers and agricultural experts. The aesthetic is **Corporate/Modern** with a heavy lean toward **Minimalism**, ensuring that complex diagnostic data remains legible and actionable under various lighting conditions (including outdoor usage). 

The emotional response should be one of "reliable expertise"—the UI acts as a digital specialist that is both approachable and scientifically rigorous. This is achieved through high-contrast typography, a restrained color palette, and a clear visual hierarchy that prioritizes the diagnosis and recommended treatment.

## Colors
This color palette is functional and semantic. The **Primary Green** (#16A34A) symbolizes healthy crops and growth, serving as the anchor for successful states and AI interactions. The **Warning Amber** and **Danger Red** are reserved strictly for disease severity levels and critical system alerts.

The background uses a "Medical White" (Gray-50) to reduce eye strain compared to pure white, while keeping the interface feeling sterile and professional. Grayscale tones are utilized to distinguish between metadata (Source chips) and primary diagnosis data.

## Typography
**Inter** is selected for its exceptional legibility in the Vietnamese language, specifically regarding diacritics which can often feel cramped in other sans-serif faces. 

The type system uses a generous line-height (1.5x to 1.6x) for body text to ensure readability for users who may be reviewing diagnosis results in field environments. Headlines use a tighter tracking and heavier weight to provide a strong "anchor" for page sections. Labels are occasionally set in uppercase or medium weights to differentiate them from body copy in information-dense cards.

## Layout & Spacing
The layout follows a **12-column fluid grid** for desktop and a **single-column vertical stack** for mobile. A strict 8px spacing system governs all margins and padding to maintain mathematical harmony.

Information is grouped into "Logical Containers" (Cards). Between cards, we use a 24px gutter. Within cards, a 16px internal padding is standard, increasing to 24px for complex disease info cards. The mobile experience prioritizes the "Diagnostic Viewfinder" and the "Chat" interface, utilizing a bottom-sheet pattern for disease details to keep the diagnosis results within thumb-reach.

## Elevation & Depth
In alignment with the medical aesthetic, depth is achieved primarily through **Tonal Layers** and **Low-contrast outlines** rather than aggressive shadows. 

The base canvas is light gray. Primary cards are white with a 1px border (#E5E7EB). Shadows are used sparingly—only for "floating" elements like the main Diagnostic Trigger Button or active Chat Bubbles. These shadows should be "Ambient": highly diffused (20px-30px blur), low opacity (5-8%), and slightly tinted with the primary green to maintain brand cohesion.

## Shapes
The shape language uses a **Rounded** (0.5rem base) philosophy. This strikes a balance between the clinical sharpness of a medical tool and the organic, approachable nature of agriculture. 

Interactive elements like buttons and input fields utilize the standard 0.5rem radius, while "Severity Badges" and "Source Chips" use a fully rounded (pill-shaped) geometry to distinguish them as discrete status indicators. Disease Info Cards utilize a 1rem radius to soften the large data blocks.

## Components

### Severity Badges
Use a pill-shaped background with high-contrast text.
- **Nhẹ (Mild):** Light Green background, Primary Green text.
- **Trung bình (Moderate):** Light Amber background, Warning Amber text.
- **Nặng (Severe):** Light Red background, Danger Red text.

### Confidence Scores
Visualized as circular progress rings. The stroke color reflects the confidence percentage (e.g., Green for >80%, Amber for 50-79%). The percentage text is centered in `label-md` bold.

### Chat Interface
- **User Bubbles:** Solid light gray background, right-aligned.
- **AI Bubbles:** White background with a 2px Primary Green border, left-aligned. This visual cue reinforces the "Doctor" persona of the AI.

### Source Reference Chips
Small, neutral chips (`label-sm`) with a leading icon representing the source type (e.g., Book icon for research papers, Link icon for web sources).

### Tabbed Disease Cards
Utilize a flat tab system at the top of the card. The active tab is indicated by a Primary Green bottom border (3px) and bold text. Content below the tabs should reflow smoothly between "Triệu chứng" (Symptoms), "Nguyên nhân" (Causes), and "Điều trị" (Treatment).

### Input Fields
Clean, outlined boxes with a 1px border. On focus, the border thickens to 2px Primary Green with a soft outer glow. Labels always sit above the field in `label-md`.