from __future__ import annotations

import json
import secrets
from typing import Any
from urllib.parse import urlparse

from .commerce import CommercePackager, official_domain, validate_commerce_brief
from .pinterest import PinterestPackager
from .store import Store, now


DESTINATIONS = {"shopee_video": "Shopee Video"}


class CommercialCenter:
    """Persistent affiliate catalog and campaign ledger. Never contacts a platform."""

    def __init__(self, store: Store, packager: CommercePackager):
        self.store = store
        self.packager = packager
        self.pinterest = PinterestPackager(store)
        self._init_schema()

    def _init_schema(self) -> None:
        with self.store.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS commerce_products (
                    id TEXT PRIMARY KEY, platform TEXT NOT NULL DEFAULT 'shopee',
                    external_id TEXT NOT NULL, title TEXT NOT NULL, product_url TEXT NOT NULL,
                    affiliate_url TEXT NOT NULL, price REAL NOT NULL DEFAULT 0,
                    currency TEXT NOT NULL DEFAULT 'BRL', price_checked_at TEXT,
                    exact_product_confirmed INTEGER NOT NULL DEFAULT 0,
                    affiliate_disclosure INTEGER NOT NULL DEFAULT 0,
                    assets TEXT NOT NULL DEFAULT '[]', claims TEXT NOT NULL DEFAULT '[]',
                    status TEXT NOT NULL, validation TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                    UNIQUE(platform, external_id)
                );
                CREATE TABLE IF NOT EXISTS commerce_campaigns (
                    id TEXT PRIMARY KEY, product_id TEXT NOT NULL, name TEXT NOT NULL,
                    destination TEXT NOT NULL, job_id TEXT, status TEXT NOT NULL DEFAULT 'draft',
                    notes TEXT NOT NULL DEFAULT '', package_file TEXT,
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                    FOREIGN KEY(product_id) REFERENCES commerce_products(id)
                );
                CREATE TABLE IF NOT EXISTS commerce_metrics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, campaign_id TEXT NOT NULL,
                    clicks INTEGER NOT NULL DEFAULT 0, conversions INTEGER NOT NULL DEFAULT 0,
                    commission REAL NOT NULL DEFAULT 0, cost REAL NOT NULL DEFAULT 0,
                    recorded_at TEXT NOT NULL,
                    FOREIGN KEY(campaign_id) REFERENCES commerce_campaigns(id)
                );
                CREATE TABLE IF NOT EXISTS commerce_distributions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, campaign_id TEXT NOT NULL,
                    destination TEXT NOT NULL, status TEXT NOT NULL,
                    manifest_file TEXT NOT NULL, settings TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                    FOREIGN KEY(campaign_id) REFERENCES commerce_campaigns(id),
                    UNIQUE(campaign_id, destination)
                );
            """)

    @staticmethod
    def _text(value: Any, label: str, maximum: int = 300) -> str:
        text = str(value or "").strip()
        if not text:
            raise ValueError(f"{label} é obrigatório")
        if len(text) > maximum:
            raise ValueError(f"{label} excede {maximum} caracteres")
        return text

    @staticmethod
    def _shopee_url(value: Any, label: str) -> tuple[str, str | None]:
        url = str(value or "").strip()
        parsed = urlparse(url)
        host = (parsed.hostname or "").lower()
        if parsed.scheme != "https" or not official_domain(host, "shopee.com.br"):
            return url, f"{label} precisa usar um endereço HTTPS oficial da Shopee Brasil"
        return url, None

    @staticmethod
    def _product(row: Any) -> dict[str, Any]:
        item = dict(row)
        for field, fallback in (("assets", []), ("claims", []), ("validation", {})):
            try:
                item[field] = json.loads(item.get(field) or json.dumps(fallback))
            except (TypeError, json.JSONDecodeError):
                item[field] = fallback
        item["exact_product_confirmed"] = bool(item["exact_product_confirmed"])
        item["affiliate_disclosure"] = bool(item["affiliate_disclosure"])
        return item

    def create_product(self, data: dict[str, Any]) -> dict[str, Any]:
        external_id = self._text(data.get("product_id"), "Identificador do produto", 120)
        title = self._text(data.get("title"), "Título do produto", 300)
        product_url, product_url_error = self._shopee_url(data.get("product_url"), "URL do produto")
        affiliate_url, affiliate_url_error = self._shopee_url(data.get("affiliate_url"), "Link de afiliado")
        try:
            price = max(0.0, float(data.get("price") or 0))
        except (TypeError, ValueError):
            raise ValueError("Preço inválido")
        assets = data.get("assets") or []
        claims = data.get("claims") or []
        if not isinstance(assets, list) or not isinstance(claims, list):
            raise ValueError("Assets e alegações precisam ser listas")
        brief = {
            "product_id": external_id,
            "title": title,
            "product_url": product_url,
            "exact_product_confirmed": bool(data.get("exact_product_confirmed")),
            "affiliate_disclosure": bool(data.get("affiliate_disclosure")),
            "assets": assets,
            "claims": claims,
        }
        validation = validate_commerce_brief(brief)
        for error in (product_url_error, affiliate_url_error):
            if error and error not in validation["errors"]:
                validation["errors"].append(error)
        validation["passed"] = not validation["errors"]
        status = "validated" if validation["passed"] else "blocked"
        timestamp = now()
        with self.store.connect() as db:
            existing = db.execute(
                "SELECT id,created_at FROM commerce_products WHERE platform='shopee' AND external_id=?",
                (external_id,),
            ).fetchone()
            product_id = str(existing["id"]) if existing else secrets.token_hex(8)
            created_at = str(existing["created_at"]) if existing else timestamp
            db.execute("""
                INSERT INTO commerce_products(id,platform,external_id,title,product_url,affiliate_url,price,currency,
                    price_checked_at,exact_product_confirmed,affiliate_disclosure,assets,claims,status,validation,
                    created_at,updated_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(platform,external_id) DO UPDATE SET
                    title=excluded.title,product_url=excluded.product_url,affiliate_url=excluded.affiliate_url,
                    price=excluded.price,price_checked_at=excluded.price_checked_at,
                    exact_product_confirmed=excluded.exact_product_confirmed,
                    affiliate_disclosure=excluded.affiliate_disclosure,assets=excluded.assets,claims=excluded.claims,
                    status=excluded.status,validation=excluded.validation,updated_at=excluded.updated_at
            """, (product_id, "shopee", external_id, title, product_url, affiliate_url, price, "BRL", timestamp,
                  int(brief["exact_product_confirmed"]), int(brief["affiliate_disclosure"]),
                  json.dumps(assets, ensure_ascii=False), json.dumps(claims, ensure_ascii=False), status,
                  json.dumps(validation, ensure_ascii=False), created_at, timestamp))
        return self.get_product(product_id)

    def get_product(self, product_id: str) -> dict[str, Any]:
        with self.store.connect() as db:
            row = db.execute("SELECT * FROM commerce_products WHERE id=?", (product_id,)).fetchone()
        if not row:
            raise ValueError("Produto comercial não encontrado")
        return self._product(row)

    def list_products(self) -> list[dict[str, Any]]:
        with self.store.connect() as db:
            rows = db.execute("SELECT * FROM commerce_products ORDER BY updated_at DESC").fetchall()
        return [self._product(row) for row in rows]

    def create_campaign(self, data: dict[str, Any]) -> dict[str, Any]:
        product = self.get_product(self._text(data.get("product_id"), "Produto", 40))
        if product["status"] != "validated":
            raise ValueError("O produto precisa passar pela validação comercial antes da campanha")
        name = self._text(data.get("name"), "Nome da campanha", 180)
        destination = str(data.get("destination") or "shopee_video").strip().lower()
        if destination not in DESTINATIONS:
            raise ValueError("Destino ainda não disponível para campanhas")
        job_id = str(data.get("job_id") or "").strip() or None
        job = self.store.get_job(job_id) if job_id else None
        if job_id and not job:
            raise ValueError("Produção vinculada não encontrada")
        status = "ready_for_package" if job and job["status"] == "approved" else "draft"
        timestamp = now()
        campaign_id = secrets.token_hex(8)
        notes = str(data.get("notes") or "").strip()[:1000]
        try:
            cost = max(0.0, float(data.get("cost") or 0))
        except (TypeError, ValueError):
            raise ValueError("Custo inválido")
        with self.store.connect() as db:
            db.execute("""INSERT INTO commerce_campaigns(id,product_id,name,destination,job_id,status,notes,created_at,updated_at)
                          VALUES(?,?,?,?,?,?,?,?,?)""",
                       (campaign_id, product["id"], name, destination, job_id, status, notes, timestamp, timestamp))
            db.execute("""INSERT INTO commerce_metrics(campaign_id,clicks,conversions,commission,cost,recorded_at)
                          VALUES(?,?,?,?,?,?)""", (campaign_id, 0, 0, 0, cost, timestamp))
        return self.get_campaign(campaign_id)

    @staticmethod
    def _campaign(row: Any) -> dict[str, Any]:
        item = dict(row)
        clicks = int(item.get("clicks") or 0)
        conversions = int(item.get("conversions") or 0)
        commission = float(item.get("commission") or 0)
        cost = float(item.get("cost") or 0)
        item["conversion_rate"] = round(100 * conversions / clicks, 2) if clicks else 0
        item["roi"] = round(100 * (commission - cost) / cost, 2) if cost else None
        item["destination_label"] = DESTINATIONS.get(item["destination"], item["destination"])
        return item

    def _campaign_query(self, where: str = "", values: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        sql = """
            WITH latest AS (SELECT campaign_id,MAX(id) AS id FROM commerce_metrics GROUP BY campaign_id)
            SELECT c.*,p.title AS product_title,p.external_id AS product_external_id,p.status AS product_status,
                   COALESCE(m.clicks,0) AS clicks,COALESCE(m.conversions,0) AS conversions,
                   COALESCE(m.commission,0) AS commission,COALESCE(m.cost,0) AS cost,m.recorded_at AS metrics_at,
                   d.status AS pinterest_status,d.manifest_file AS pinterest_package_file,
                   d.updated_at AS pinterest_updated_at
            FROM commerce_campaigns c JOIN commerce_products p ON p.id=c.product_id
            LEFT JOIN latest l ON l.campaign_id=c.id
            LEFT JOIN commerce_metrics m ON m.id=l.id
            LEFT JOIN commerce_distributions d ON d.campaign_id=c.id AND d.destination='pinterest_video'
        """
        if where:
            sql += " WHERE " + where
        sql += " ORDER BY c.updated_at DESC"
        with self.store.connect() as db:
            rows = db.execute(sql, values).fetchall()
        return [self._campaign(row) for row in rows]

    def get_campaign(self, campaign_id: str) -> dict[str, Any]:
        rows = self._campaign_query("c.id=?", (campaign_id,))
        if not rows:
            raise ValueError("Campanha não encontrada")
        return rows[0]

    def list_campaigns(self) -> list[dict[str, Any]]:
        return self._campaign_query()

    def record_metrics(self, campaign_id: str, data: dict[str, Any]) -> dict[str, Any]:
        campaign = self.get_campaign(campaign_id)
        try:
            clicks = max(0, int(data.get("clicks") or 0))
            conversions = max(0, int(data.get("conversions") or 0))
            commission = max(0.0, float(data.get("commission") or 0))
            cost = max(0.0, float(data.get("cost") or 0))
        except (TypeError, ValueError):
            raise ValueError("Métricas comerciais inválidas")
        if conversions > clicks:
            raise ValueError("Conversões não podem superar os cliques")
        timestamp = now()
        with self.store.connect() as db:
            db.execute("""INSERT INTO commerce_metrics(campaign_id,clicks,conversions,commission,cost,recorded_at)
                          VALUES(?,?,?,?,?,?)""", (campaign["id"], clicks, conversions, commission, cost, timestamp))
            db.execute("UPDATE commerce_campaigns SET updated_at=? WHERE id=?", (timestamp, campaign["id"]))
        return self.get_campaign(campaign["id"])

    def prepare_campaign(self, campaign_id: str, duration: int = 30) -> dict[str, Any]:
        campaign = self.get_campaign(campaign_id)
        if not campaign.get("job_id"):
            raise ValueError("Vincule uma produção aprovada antes de preparar o pacote")
        product = self.get_product(campaign["product_id"])
        package = self.packager.prepare(campaign["job_id"], {
            "product_id": product["external_id"], "title": product["title"],
            "product_url": product["product_url"], "affiliate_url": product["affiliate_url"],
            "exact_product_confirmed": product["exact_product_confirmed"],
            "affiliate_disclosure": product["affiliate_disclosure"], "assets": product["assets"],
            "claims": product["claims"],
        }, duration)
        timestamp = now()
        with self.store.connect() as db:
            db.execute("UPDATE commerce_campaigns SET status='packaged',package_file='commerce-package.json',updated_at=? WHERE id=?",
                       (timestamp, campaign_id))
        return {"campaign": self.get_campaign(campaign_id), "package": package,
                "automatic_upload_allowed": False}

    def prepare_pinterest(self, campaign_id: str, data: dict[str, Any] | None = None) -> dict[str, Any]:
        campaign = self.get_campaign(campaign_id)
        if not campaign.get("job_id"):
            raise ValueError("Vincule uma produção aprovada antes de preparar o Video Pin")
        product = self.get_product(campaign["product_id"])
        if campaign.get("status") != "packaged":
            self.prepare_campaign(campaign_id, int((data or {}).get("duration", 30)))
            campaign = self.get_campaign(campaign_id)
        package = self.pinterest.prepare(campaign, product, data)
        timestamp = now()
        settings = {key: (data or {}).get(key) for key in ("board_name", "title", "description", "alt_text")
                    if (data or {}).get(key)}
        with self.store.connect() as db:
            db.execute("""
                INSERT INTO commerce_distributions(campaign_id,destination,status,manifest_file,settings,created_at,updated_at)
                VALUES(?,?,?,?,?,?,?)
                ON CONFLICT(campaign_id,destination) DO UPDATE SET status=excluded.status,
                    manifest_file=excluded.manifest_file,settings=excluded.settings,updated_at=excluded.updated_at
            """, (campaign_id, "pinterest_video", "prepared", "pinterest-package.json",
                  json.dumps(settings, ensure_ascii=False), timestamp, timestamp))
        return {"campaign": self.get_campaign(campaign_id), "package": package,
                "automatic_upload_allowed": False, "login_required": True}

    def overview(self) -> dict[str, Any]:
        products = self.list_products()
        campaigns = self.list_campaigns()
        commission = round(sum(float(item["commission"]) for item in campaigns), 2)
        cost = round(sum(float(item["cost"]) for item in campaigns), 2)
        conversions = sum(int(item["conversions"]) for item in campaigns)
        return {
            "mode": "manual-safe", "automatic_upload_allowed": False,
            "summary": {"products": len(products), "validated_products": sum(item["status"] == "validated" for item in products),
                        "campaigns": len(campaigns), "packaged": sum(item["status"] == "packaged" for item in campaigns),
                        "clicks": sum(int(item["clicks"]) for item in campaigns), "conversions": conversions,
                        "commission": commission, "cost": cost, "profit": round(commission - cost, 2)},
            "products": products, "campaigns": campaigns,
            "destinations": [{"id": key, "label": label, "available": True} for key, label in DESTINATIONS.items()] +
                            [{"id": "pinterest_video", "label": "Pinterest Video Pin", "available": True,
                              "automatic_upload_allowed": False, "login_required": True}],
            "safety": "Somente produtos, mídia e alegações validados entram em campanhas; nenhum upload é realizado.",
        }
