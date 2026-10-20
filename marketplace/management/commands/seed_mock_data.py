import json
import random
import math
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models.signals import post_save, m2m_changed

from marketplace.models import (
    CustomUser,
    Developer,
    Category,
    OperatingSystem,
    Application,
)
from marketplace.signals import (
    index_application_on_save,
    index_application_on_category_change,
)


class Command(BaseCommand):
    help = (
        "Seed the database with mock Categories, Operating Systems, Developers, "
        "and Applications safely without triggering runaway background API threads."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--apps",
            type=int,
            default=100,
            help="Number of mock applications to create (default: 100)",
        )
        parser.add_argument(
            "--mock-embeddings",
            action="store_true",
            help="Generate synthetic normalized 768-dim embeddings so vector search works offline.",
        )
        parser.add_argument(
            "--fixture",
            help=(
                "Path to a JSON list of apps ({name, description, category, os, price}) "
                "to create instead of random ones, e.g. marketplace/fixtures/demo_apps.json. "
                "Run backfill_embeddings afterwards to embed them."
            ),
        )
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Clear existing mock applications, categories, and OS before seeding.",
        )

    def handle(self, *args, **options):
        app_count = options["apps"]
        mock_embeddings = options["mock_embeddings"]
        clear = options["clear"]

        self.stdout.write(self.style.NOTICE("=== Starting CloudMarket Seeding Process ==="))

        # -------------------------------------------------------------
        # 1. TEMPORARILY DISCONNECT SIGNALS
        # CRUCIAL: Otherwise saving 100 apps spawns 200+ background threads
        # hitting Gemini API concurrently and blowing up connection pools!
        # -------------------------------------------------------------
        self.stdout.write("Temporarily disconnecting embedding background signals...")
        post_save.disconnect(index_application_on_save, sender=Application)
        m2m_changed.disconnect(
            index_application_on_category_change,
            sender=Application.categories.through,
        )

        try:
            with transaction.atomic():
                if clear:
                    self.stdout.write(self.style.WARNING("Clearing existing applications..."))
                    Application.objects.all().delete()

                # -------------------------------------------------------------
                # 2. CREATE / ENSURE OPERATING SYSTEMS
                # -------------------------------------------------------------
                os_names = ["Windows", "macOS", "Linux", "Android", "iOS", "Web / Cloud"]
                os_instances = []
                for name in os_names:
                    os_obj, created = OperatingSystem.objects.get_or_create(os_name=name[:25])
                    os_instances.append(os_obj)
                    if created:
                        self.stdout.write(f"  [+] Created OS: {name}")

                # -------------------------------------------------------------
                # 3. CREATE / ENSURE CATEGORIES
                # Note: Category.description has unique=True in models.py!
                # -------------------------------------------------------------
                categories_data = [
                    ("Productivity", "Tools and software designed to streamline your daily workflow and tasks."),
                    ("Developer Tools", "Compilers, debuggers, IDEs, code editors, and software utilities for devs."),
                    ("Design & Media", "Creative graphics suites, vector illustration, video, and audio workstations."),
                    ("Security & VPN", "Protection utilities, privacy shields, firewalls, and cryptographic tools."),
                    ("Business & Finance", "Invoicing, bookkeeping, asset management, and enterprise analytics suites."),
                    ("AI & Machine Learning", "Intelligent assistants, prompt tools, LLM frontends, and predictive models."),
                    ("Education & Study", "Interactive learning platforms, flashcards, reference, and tutorials."),
                    ("Health & Fitness", "Activity trackers, nutrition guides, workout logs, and meditation apps."),
                    ("Utilities & System", "Disk cleaners, clipboard managers, file archivers, and benchmark tools."),
                    ("Communication", "Team chats, video conferencing, email clients, and collaboration hubs."),
                ]
                category_instances = []
                for cat_name, cat_desc in categories_data:
                    cat_obj, created = Category.objects.get_or_create(
                        category_name=cat_name[:25],
                        defaults={"description": cat_desc[:150]},
                    )
                    category_instances.append(cat_obj)
                    if created:
                        self.stdout.write(f"  [+] Created Category: {cat_name}")

                # -------------------------------------------------------------
                # 4. CREATE / ENSURE MOCK DEVELOPERS
                # Application.developer cannot be null!
                # -------------------------------------------------------------
                dev_configs = [
                    ("dev_nexus", "nexus@cloudmarket.dev", "Nexus Soft"),
                    ("dev_zenith", "zenith@cloudmarket.dev", "Zenith Labs"),
                    ("dev_aurora", "aurora@cloudmarket.dev", "Aurora Studio"),
                    ("dev_pixel", "pixel@cloudmarket.dev", "PixelCraft"),
                    ("dev_hyper", "hyper@cloudmarket.dev", "HyperByte"),
                ]
                developer_instances = []
                for username, email, alias in dev_configs:
                    user, user_created = CustomUser.objects.get_or_create(
                        username=username,
                        defaults={
                            "email": email,
                            "first_name": alias.split()[0],
                            "last_name": alias.split()[-1] if len(alias.split()) > 1 else "Dev",
                            "user_type": "developer",
                            "country": "US",
                        },
                    )
                    if user_created:
                        user.set_password("DevPassword123!")
                        user.save()

                    dev_profile, dev_created = Developer.objects.get_or_create(
                        user=user,
                        defaults={
                            "developer_alias": alias[:15],
                            "payment_method": "card",
                            "payment_details": f"stripe_acc_{alias[:10]}",
                        },
                    )
                    developer_instances.append(dev_profile)

                self.stdout.write(f"  Ready with {len(developer_instances)} developer accounts.")

                if options["fixture"]:
                    self._seed_from_fixture(
                        options["fixture"], developer_instances, category_instances, os_instances
                    )
                    return

                # -------------------------------------------------------------
                # 5. GENERATE 100 UNIQUE MOCK APPS
                # Constraint: app_name max_length=25 and unique=True!
                # -------------------------------------------------------------
                prefixes = [
                    "Nova", "Apex", "Omni", "Pulse", "Zen", "Swift", "Hyper", "Vivid", "Core", "Meta",
                    "Echo", "Flux", "Sync", "Cyber", "Aero", "Prime", "Quantum", "Volt", "Terra", "Atlas",
                    "Spectra", "Byte", "Orbit", "Prism", "Helix", "Sol", "Titan", "Vertex", "Krypton", "Strata",
                ]
                suffixes = [
                    "Flow", "Desk", "Studio", "Pro", "Hub", "Pad", "Craft", "Vault", "Grid", "Space",
                    "Lens", "Dock", "Mate", "Base", "Cast", "Wave", "Sync", "Note", "Mind", "View",
                ]

                # Generate unique candidate names
                candidate_names = []
                for p in prefixes:
                    for s in suffixes:
                        candidate_names.append(f"{p} {s}")

                random.shuffle(candidate_names)

                # Filter out names already in DB
                existing_names = set(Application.objects.values_list("app_name", flat=True))
                valid_names = [n for n in candidate_names if n not in existing_names and len(n) <= 25]

                if len(valid_names) < app_count:
                    # Append numbers if we need more unique names
                    idx = 1
                    while len(valid_names) < app_count:
                        cand = f"App-{idx} {random.choice(suffixes)}"[:25]
                        if cand not in existing_names and cand not in valid_names:
                            valid_names.append(cand)
                        idx += 1

                descriptions = [
                    "A high-performance modern workspace designed for effortless multitasking and team efficiency.",
                    "Comprehensive utility suite featuring real-time diagnostic telemetry, security scanning, and cleanup.",
                    "Creative design studio with vector curves, raster layers, SVG export, and responsive canvas presets.",
                    "Developer-centric distraction-free code editor with integrated LSP server, terminal, and git sync.",
                    "Smart personal finance manager with automated expense classification, recurring bills, and ledger export.",
                    "Privacy-first communication client featuring end-to-end encrypted chats and low-latency voice rooms.",
                    "AI-assisted research companion that organizes lecture notes, summarizes research PDFs, and creates flashcards.",
                    "Cross-platform audio mastering tool with parametric EQ, multiband compression, and loudness metering.",
                    "Lightweight file synchronization service with cloud drive mounting, peer-to-peer relay, and snapshots.",
                    "Full-featured database administration GUI supporting Postgres, SQLite, Redis, and schema visualization.",
                ]

                created_apps = []
                self.stdout.write(f"Generating {app_count} applications...")

                for i in range(app_count):
                    app_name = valid_names[i]
                    dev = random.choice(developer_instances)
                    price = Decimal(random.choice([0.00, 0.00, 4.99, 9.99, 14.99, 19.99, 29.99, 49.99]))
                    rating = round(random.uniform(3.2, 5.0), 1)
                    downloads = random.randint(10, 25000)
                    desc = f"{random.choice(descriptions)} {random.choice(descriptions)}"[:990]

                    # Mock embedding: generate a random unit-normalized vector of 768 dims
                    embedding = None
                    if mock_embeddings:
                        vec = [random.gauss(0, 1) for _ in range(768)]
                        norm = math.sqrt(sum(x * x for x in vec))
                        embedding = [x / norm for x in vec] if norm > 0 else vec

                    app = Application(
                        developer=dev,
                        app_name=app_name,
                        app_description=desc,
                        price=price,
                        rating=rating,
                        downloads=downloads,
                        embedding=embedding,
                    )
                    created_apps.append(app)

                # Bulk insert applications
                Application.objects.bulk_create(created_apps)

                # Query back the created apps to attach ManyToMany relationships
                saved_apps = list(Application.objects.filter(app_name__in=[a.app_name for a in created_apps]))
                app_lookup = {a.app_name: a for a in saved_apps}

                # Associate Categories and OS
                for app_stub in created_apps:
                    db_app = app_lookup.get(app_stub.app_name)
                    if db_app:
                        # 1 to 3 categories
                        assigned_cats = random.sample(category_instances, k=random.randint(1, min(3, len(category_instances))))
                        db_app.categories.set(assigned_cats)

                        # 1 to 4 OSes
                        assigned_os = random.sample(os_instances, k=random.randint(1, min(4, len(os_instances))))
                        db_app.os.set(assigned_os)

            self.stdout.write(self.style.SUCCESS(
                f"\nSuccessfully seeded:\n"
                f"  - {len(os_instances)} Operating Systems\n"
                f"  - {len(category_instances)} Categories\n"
                f"  - {len(developer_instances)} Developers\n"
                f"  - {app_count} Applications (all with OS and Categories linked)"
            ))

            if not mock_embeddings:
                self.stdout.write(self.style.NOTICE(
                    "\nNote: Apps were created with embedding=None to save API quota.\n"
                    "To generate real AI embeddings via Gemini, run:\n"
                    "  python manage.py backfill_embeddings\n"
                    "Or pass --mock-embeddings next time for synthetic vectors."
                ))

        finally:
            # -------------------------------------------------------------
            # 6. ALWAYS RECONNECT SIGNALS
            # -------------------------------------------------------------
            self.stdout.write("Reconnecting embedding background signals...")
            post_save.connect(index_application_on_save, sender=Application)
            m2m_changed.connect(
                index_application_on_category_change,
                sender=Application.categories.through,
            )
            self.stdout.write(self.style.SUCCESS("=== Seeding complete! ==="))

    def _seed_from_fixture(self, path, developers, categories, operating_systems):
        """Create apps from a JSON fixture; apps whose name already exists are skipped."""
        with open(path, encoding="utf-8") as f:
            entries = json.load(f)

        category_by_name = {c.category_name: c for c in categories}
        os_by_name = {o.os_name: o for o in operating_systems}
        existing = set(Application.objects.values_list("app_name", flat=True))

        new_entries = [e for e in entries if e["name"] not in existing]
        apps = Application.objects.bulk_create([
            Application(
                developer=random.choice(developers),
                app_name=e["name"][:25],
                app_description=e["description"],
                price=Decimal(str(e.get("price", 0))),
                rating=round(random.uniform(3.2, 5.0), 1),
                downloads=random.randint(10, 25000),
            )
            for e in new_entries
        ])

        # bulk_create skips m2m_changed, so no embedding threads are started
        category_links, os_links = [], []
        for app, e in zip(apps, new_entries):
            category_links.append(Application.categories.through(
                application_id=app.pk, category_id=category_by_name[e["category"]].pk,
            ))
            for os_name in e["os"]:
                os_links.append(Application.os.through(
                    application_id=app.pk, operatingsystem_id=os_by_name[os_name].pk,
                ))
        Application.categories.through.objects.bulk_create(category_links)
        Application.os.through.objects.bulk_create(os_links)

        self.stdout.write(self.style.SUCCESS(
            f"Created {len(apps)} apps from {path} "
            f"({len(entries) - len(new_entries)} already existed). "
            "Run 'python manage.py backfill_embeddings' to embed them."
        ))
