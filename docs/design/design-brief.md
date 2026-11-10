# Design brief: Altai on the Park portal homepage

Updated 2026-11-10 · Research only, nothing built · Screenshots in `references/` (desktop 1440 wide, mobile 390 wide, headless Chrome, cut off at 9000px tall)

Owner's ask: **green, with trees and the park behind it, "so it looks like you're on the park".**

---

## §1 Brand tokens

### What Altai's own material shows

**There's no logo, colours, brochure or website for the building online.** Here's what is known:

- **Name:** listings spell it **"Alatai on the Park"**. Our project files say "Altai". **Ask Michael which spelling is right before anything goes live.**
- **Address:** 391 Wickham Terrace, Spring Hill QLD 4000. Six storeys, 48 apartments, many of them dual-key studios. Shops on the ground floor. Spring Hill Loop bus (route 30) stops out front.
- **Park:** listings sell "Parkland Views" and "Great location on city fringe and parkland". It's near Roma Street Parkland (the old Albert Park, beside Wickham Terrace) and Wickham Park. Nothing confirms which park the windows face. **Check with Michael.**
- **Developer:** not found. From the listing photo it looks like a 1970s–80s building, but that isn't confirmed.
- **Facade colours:** off-white, with slate-navy and powder-blue vertical panels. A green palette won't clash with them. Keep blue out of the portal so it doesn't look like a second brand.
- **Photos online:** agents' listing shots only. They're bright, HDR, wide-angle and taken under blue skies, and the agents own them, so **we can't use them.** Source URLs (looked at, not downloaded):
  - https://images.reip.com.au/listings/406391-wickham-terrace-spring-hill-qld-4000/888/12760888_img_01_m.jpg (street view of the building)
  - https://portal.reip.com.au/real-estate/property/12760888-406391-wickham-terrace-spring-hill-qld-4000 (listing text: 48 apartments, parkland)
  - https://www.ratemyagent.com.au/property/504-504a-391-wickham-terrace-spring-hill-qld-4000-4ssqr ("Alatai on the Park", "Top Floor – Parkland Views". Blocks fetches, so only the search snippet was seen.)
- **Earlier draft:** `docs/design.html` uses `--brand #1f4d3a` and `--accent #c9a227` (gold). The palette below keeps a deep green and drops the gold.

### Proposed park palette (none found, so this is sampled from the best park-side references)

Each colour below was read from the live site's computed CSS, not guessed. Contrast figures are against Paper.

| Token | Hex | Where it came from | Use | Contrast |
|---|---|---|---|---|
| **Canopy** | `#243B2F` | Botanic Gardens of Sydney: headings, colour cards, footer | Main brand colour: header band, footer, primary button, headings | 11.2 : 1 |
| **Fig** | `#17493B` | Lendlease: green lead tile and buttons | Links, hover state, a second green surface | 9.5 : 1 |
| **Olive** | `#898F4E` | Eighteen Park (East Brisbane, park-side): hero panel and linocut ink | Illustration ink, hairlines, big display text only (**not** small text) | 3.2 : 1 |
| **Olive text** | `#5E6336` | Darker Olive (my adjustment, not sampled) | Small labels where Olive is wanted | 5.9 : 1 |
| **Sage** | `#7A8980` | TCL landscape architects: panels and footer | Dividers, muted icons, map lines (not body text) | 3.4 : 1 |
| **Mint wash** | `#E6F3E4` | Botanic Gardens of Sydney: soft panel | Status panels ("With the committee"), selected rows | Canopy on it 10.5 : 1 |
| **Paper** | `#F9F7EF` | Botanic Gardens of Sydney: cream band | Page background | – |
| **Stone** | `#F3EEE7` | Aman: page background | Alternate section band | – |
| **Ink** | `#22272B` | Botanic Gardens of Sydney: body text | Body text | 14.1 : 1 |
| **Rust** (signal) | `#C02B0A` | Eighteen Park: accent text | Overdue or missed legal deadline only | 5.5 : 1 |

Rule: Canopy and Paper make up the page. Olive, Sage and Mint are small touches. Rust only means "late".

### Type seen on the best references

| Site | Display | Text |
|---|---|---|
| Aria | Signifier 400, 32–40px | Söhne-style "scto" 300/400, 14–18px |
| Spyre | Ivy Presto Display 100, 80px, italic second line | Montserrat 300, 14px, +0.7px tracking |
| Gardner Vaughan | Feature Deck 400, 47px | Inter 400, 17.5px |
| The Calile | Beausite Light 300, 30–32px | Brown 300, 13–15px |
| Aman | Lyon Display | Whitney 14px; small-caps labels |
| Eighteen Park | Epicene Display 500, 40px | National 2 |
| Botanic Gardens Sydney | GardensInkTrap 500, 68px | Inter 16px |

Every one pairs **a light serif for headings** with **a quiet sans for everything else**.

**Free web-font pairing (Google Fonts):**
- **First choice:** **Newsreader** (headings, 300–400, closest free match to Signifier and Lyon) with **Hanken Grotesk** (body and interface, 400/500, close to National 2 and Brown).
- **Easier to read (older owners on phones):** **Source Serif 4** (display sizes, 400) with **Public Sans** (400/600).
- Don't use weights under 300 for headings. Spyre's 100 weight looks beautiful but is hard to read on a phone.

---

## §2 Reference sites

Pages: **product site** = the public BodyCorp site (`index.html`) · **portal landing** = Altai's own sign-in page (`portal.html?b=altai` before sign-in) · **resident home** = the first screen after sign-in.

| URL | What to steal (one thing) | Which page | Notes (what to avoid) |
|---|---|---|---|
| https://eighteenpark.com.au/ (`eighteen-park`) | **Split hero:** one half flat Olive with the name in a serif, the other half a two-colour linocut of park trees framing the city. The canopy *frames* the view. | Portal landing hero | Everything below the hero stays blank until scroll animations run (the screenshot is empty there). Never hide content until scroll. Leave out the pink. |
| https://ariaproperty.com.au/ (`aria`) | **Full-width garden image band between sections**, with only a tiny white caption bottom-left ("→ Discover Sanctuary Residences"). No overlay, box or button on the photo. | Product site and portal landing | The video hero was a blank white 900px in headless. On mobile the floating "Enquire now" pill covers the headline. |
| https://thecalilehotel.com/ (`calile`) | **Staggered editorial rows:** a short heading with a 40px hairline after it, a small text block, and photos stepped at different heights and sizes. | Product site ("how it works" story) | Day-mode toggle sits over the copy on mobile. The figure illustrations are too playful for a body corporate. |
| https://www.aman.com/ (`aman`) | **Section header recipe:** tiny letter-spaced label, then a light serif title, then an underlined "Discover more" text link, all on warm Stone. | Resident home section headers (e.g. NOTICES / Lift service Thursday / Read notice) | Cookie dialog covers the top (not dismissed). The video hero shows "Player error". |
| https://www.botanicgardens.org.au/ (`botanic-gardens-sydney`) | **Photo with an offset solid-colour card overlapping it**, and a full-width bar along the card's foot ("See what's on +"). Text never sits on the photo. | Portal landing (under the hero) and resident home "Your building" block | The Acknowledgement of Country overlay needs a click and covers the hero. Pink, blue and purple cards: keep to one green family. |
| https://www.rbg.vic.gov.au/ (`rbg-victoria`) | **"Plan your visit" card:** arrow link list, then opening hours, then location, then a notice strip with an (i). It's practical, not pretty. | Resident home "Building info" card (manager hours, office, after-hours number, current notice) | Event pill tags, coloured bottom borders on cards, the hot-pink hero. A browser-warning bar showed in headless. |
| https://gardnervaughan.com.au/ (`gardner-vaughan`) | **Row layout:** big serif name on the left, place, one line and a small link on the right, hairline between rows, on Stone. | Resident home "My requests" list (ALT-0042 in serif on the left; topic, status and deadline on the right) | Script-font slogan. Video hero shows "Player error". |
| https://www.spyregroup.com.au/ (`spyre`) | **Two-line headline in a thin serif with the second line in italic**, then one short centred paragraph and a lot of space. | Portal landing headline ("Altai on the Park / *your building, on the park*") | 80px at weight 100 is too thin for owners on phones. Use 300–400. Video hero didn't render. |
| https://www.lendlease.com/ (`lendlease`) | **Solid green lead tile at the start of a news row** ("News & Insights · See more"), followed by plain cards. | Resident home notices row (green "Notices · See all" tile, then the 3 latest) | Cookie banner covers the hero (not dismissed). Dull grey photo cards. |
| https://www.strataplan.com.au/ (`strataplan`) | **Portal pitch in one line:** "Everything about your building, in one app." Then one sentence on what's inside (levies, minutes, documents) and Register / Portal Login. "Portal" also sits in the main nav. | Product site, plus copy on the portal landing | Chat bubble and Google rating badge sit over the text. Icon "values" row. Stock photo of a man in a teal cape. |
| https://whittles.com.au/ (`whittles`) | **"Owner's Portal" in the top utility bar**, beside the phone number, so it's always one click away. | Product site header ("Sign in to your building") | Yellow parallelogram outlines, dot swarms, couple-on-couch stock photo. |
| https://netstrata.com.au/ (`netstrata`) | **"We are here to help" list:** full-width rows with a label and an arrow, separated by hairlines. | Resident home "Start a request" list (Keep a pet → / Report an accident → …) | Video hero failed. Awards strip, stats row, icon grid. |
| https://www.stratamax.com.au/Portal/login.aspx (`stratamax-portal`) | **Sign-in page carries only three things:** Sign in, Quick pay and one tip. That's all an owner needs there. | Portal landing (content only) | Everything visual: bevelled gradient buttons, boxed panels, grey frame. It's the dated look we're replacing. |
| https://civium.com.au/ (`civium`) | **A strata firm can own deep forest green** (`#133D33`). See the "Get in touch" panel. | Product site (shows the category accepts green) | Neon green `#3ED34F` buttons, icon rows, office stock photos. This is the template version of green. |
| https://www.tcl.net.au/ (`tcl`) | **Restraint:** sage plus warm grey, centred text with em-dash dividers. Palette source only. | – | Acknowledgement overlay covers the page (not dismissed). Text-only below it. |
| https://www.frasersproperty.com.au/ (`frasers`) | Nothing. **Avoid example.** | – | "Why Frasers" icon-in-circle grid, red/white template, crowded search hero. |
| https://picagroup.com.au/ (`pica`) | Nothing. **Avoid example.** | – | Flat city illustration, icon tiles, orange buttons, rating badge, slider arrows. |
| https://bcsystems.com.au/ (`bcsystems`) | Nothing. **Avoid example.** | – | Staff-photo mosaic hero, red label tiles over stock photos, review wall. |

Also checked and dropped: Mirvac, Sekisui House, Pradella, Ray Group, Arden, Milieu, Gurner, VIVO Stones Corner, Sanctuary Residences, BuildingLink, Jackalope. Reasons: template-like, dated, video or lazy-loading left them blank, or a pop-up covered the page. **Aria's pages are the strongest Brisbane park-and-garden reference. Eighteen Park is the strongest "on the park" idea.**

---

## §3 Crafted vs AI-made

### What makes the good ones feel crafted

- **Photography:** real places in natural light, set full width with square corners and no shadows (Aria, Calile, Gardner Vaughan). Paired images come in **different sizes**: one landscape beside one tall portrait. No photos of people smiling at laptops.
- **One photo per idea.** Aria puts a single full-width garden band between sections and lets it breathe, with no text on it except a tiny caption.
- **Whitespace:** large gaps between sections (about 120–160px desktop, 64–80px mobile on Aria and Spyre). Text columns are narrow (about 45–65 characters).
- **Type:** light serif headings (300–400) at 32–48px on desktop. Line-height about 1.15. Body 15–18px sans. Labels 11–12px uppercase with +0.1em tracking (Aman, Calile "BOOKINGS"). An italic second line for emphasis (Spyre), never bold.
- **Nav:** logo on the left, at most one or two words, and a menu icon (Aria). The portal sign-in is a plain text link in a thin utility bar (Whittles).
- **CTAs:** mostly **text links with an arrow** ("→ View project", Aria) or **underlined** ("Discover more", Aman). Only one filled button per screen, with square or 2–4px corners and a dark fill (Aman "Reserve", Calile "BOOKINGS").
- **Hairlines, not cards.** Aria splits columns and list rows with 1px lines. Calile puts a short rule after headings. RBG Victoria and Netstrata use arrow-row lists. Cards with drop shadows are a template sign.
- **Colour in blocks, not gradients.** A section is either Paper or solid Canopy (Botanic Gardens, Eighteen Park). No fades.
- **Motion:** where there's any, it's a slow fade on scroll. **But** Eighteen Park, Milieu and Pradella rendered blank below the fold because content waits for the animation. **Content must show without JavaScript animation.**
- **No video heroes.** Aria, Gardner Vaughan, Netstrata, Arden and Aman all showed a blank or "Player error" hero in headless. A still photo always loads.

### AI-template tells to avoid (each one seen on a live site)

- Icon-in-circle feature grids (Frasers "Why Frasers", PICA, Civium, Netstrata, Strata Plan values row).
- Rounded pill buttons in a bright accent (VIVO's orange pills, Sekisui, Civium's neon green).
- Pill tags on cards (RBG Victoria event tags).
- Centred hero with two buttons, or with a search box (Civium, Strata Plan).
- Stock people at laptops or on couches (BCsystems, Civium, Whittles).
- Things floating over content: chat bubbles, rating badges, cookie bars (Strata Plan, PICA).
- Decorative shapes: parallelogram outlines, dot swarms, gradient blobs (Whittles).
- Stats rows ("30 years · 95% · 50+") (Netstrata).
- Flat cartoon cityscapes (PICA).
- Green gradient overlay over a stock forest, emoji, AI-generated trees.

---

## §4 Imagery plan: "on the park"

### What works, and how the references do it

1. **A real photo of *this* park, taken from or beside the building.** It's the only image that's actually "on the park". **Ask Michael (or Edward on a visit) for 10–20 phone photos:** landscape, early morning or late afternoon, looking from the building or the footpath into the canopy. Include some with lots of sky, some up through the leaves, and one of the building seen through the trees.
2. **Hero (portal landing):** full-width park photo cropped so **the canopy fills the top 30–40%** and a calm patch of lawn, path or sky sits where the text goes (Aria's garden bands). Text goes on a **solid Canopy panel that overlaps the photo's bottom-left** (Botanic Gardens offset card), not straight on leaves. If text must sit on the photo, use only a short dark fade along the bottom edge (no full green overlay).
3. **The Eighteen Park idea:** a **two-colour treatment of the canopy** (Canopy green on Paper, like a linocut or duotone) as the frame around the building name. This works well for the sign-in page and keeps file sizes small.
4. **Resident home:** no big hero. Use a **narrow canopy strip (160–200px)** in duotone behind the building name, then straight into notices and requests. People come to do something, not to look at photos.
5. **Texture:** dappled leaf shadow at 6–10% opacity on one or two Paper sections (the Calile's sunlit warmth). Use it sparingly, never behind body text.
6. **Mobile:** use a portrait crop looking up into the canopy, not a squashed landscape.

### Candidate free-licence images (each page checked live 2026-11-10)

| Image | Licence | Fit |
|---|---|---|
| **Roma Street Parkland from the lookout**, Andrew Mercer, 9504×6336. https://commons.wikimedia.org/wiki/File:Roma_Street_Parkland_-_AndrewMercer_-_DSC01584.jpg | **CC BY-SA 4.0:** credit required, and an edited version (e.g. duotone) must also be CC BY-SA | Best real local park photo: lake, palms, jacaranda, Spring Hill towers. Portal landing hero until Michael's photos arrive. |
| **Bunya pines in fog, Wickham Park, Spring Hill**, John Robert McPherson, 4000×3000. https://commons.wikimedia.org/wiki/File:Araucaria_bidwillii_Agathis_robusta_in_fog_sihouette_Wickham_Park_Spring_Hill_P1140258.jpg | **CC BY-SA 4.0** (same terms) | Tree silhouettes against soft sky, right next door. Ideal for the two-colour canopy frame or a dark Canopy band. |
| **Moreton Bay fig in a park**, Nicola J Walker (taken in Sydney's Botanic Gardens). https://unsplash.com/photos/7rDVc8ojySU | **Unsplash License:** free, no credit needed | The classic Australian park tree, with spreading limbs. Use for the product site, since it isn't Brisbane. |
| **Canopy with dark, gnarled branches**, Hooman Being (portrait). https://unsplash.com/photos/verdant-green-tree-canopy-with-dark-gnarled-branches-YtdbRKv0uco | **Unsplash License** | Mobile hero and canopy strip. Takes duotone well. |
| **Looking up through canopy to sky**, zephyr skye (landscape). https://unsplash.com/photos/looking-up-through-lush-green-tree-canopy-towards-sky-nw0rX514BtU | **Unsplash License** | Desktop canopy strip behind the building name. |
| **Dappled leaf shadows on a beige wall**, Augustine Wong. https://unsplash.com/photos/dappled-leaf-shadows-on-beige-wall-njhPkg0Oe5M | **Unsplash License** | Low-opacity texture only. |

Notes:
- Unsplash pages were confirmed through a page fetch and the image previews loaded. Unsplash's bot check blocks headless screenshots of the pages themselves.
- Not recommended: "green trees near grey concrete pathway" (Yukiko Kanada). It's Anzac Square, a war memorial, so the wrong mood and not Altai's park.
- If the CC BY-SA photos are used, add one credit line in the footer, e.g. "Park photo: Andrew Mercer, CC BY-SA 4.0".
