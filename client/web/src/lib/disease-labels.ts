/**
 * Vietnamese display labels for CV disease classes.
 *
 * Source of truth mirrors backend `rag-engine/rag/core/disease_map.py` (CLASS_TO_VN).
 * The 25 classes are fixed by the trained ensemble, so a static table is correct here.
 *
 * Class ids carry no diacritics (e.g. "Ngo_benh_chay_la_lon"); deriving the display
 * name by splitting on "_" can never recover accents — it must be looked up.
 */

interface DiseaseLabel {
  crop: string;
  disease: string;
}

const CROP_LABEL: Record<string, string> = {
  cafe: "Cà phê",
  coffee: "Cà phê",
  lua: "Lúa",
  rice: "Lúa",
  mia: "Mía",
  sugarcane: "Mía",
  ngo: "Ngô",
  corn: "Ngô",
};

const DISEASE_LABELS: Record<string, DiseaseLabel> = {
  Cafe_benh_dom_rong: { crop: "Cà phê", disease: "Bệnh đốm rong" },
  Cafe_benh_nam_ri_sat: { crop: "Cà phê", disease: "Bệnh nấm rỉ sắt" },
  Cafe_benh_phan_trang: { crop: "Cà phê", disease: "Bệnh phấn trắng" },
  Cafe_benh_phoma: { crop: "Cà phê", disease: "Bệnh phoma" },
  Cafe_benh_sau_ve_bua: { crop: "Cà phê", disease: "Bệnh sâu vẽ bùa" },
  Cafe_khoe_manh: { crop: "Cà phê", disease: "Khỏe mạnh" },
  Lua_benh_dao_on_co_bong: { crop: "Lúa", disease: "Bệnh đạo ôn cổ bông" },
  Lua_benh_dao_on_la: { crop: "Lúa", disease: "Bệnh đạo ôn lá" },
  Lua_benh_dom_nau: { crop: "Lúa", disease: "Bệnh đốm nâu" },
  Lua_benh_sau_gai_hispa: { crop: "Lúa", disease: "Bệnh sâu gai hispa" },
  Lua_benh_vang_la_tungro: { crop: "Lúa", disease: "Bệnh vàng lá tungro" },
  Lua_khoe_manh: { crop: "Lúa", disease: "Khỏe mạnh" },
  Mia_benh_choi_co: { crop: "Mía", disease: "Bệnh chồi cỏ" },
  Mia_benh_dom_nau: { crop: "Mía", disease: "Bệnh đốm nâu" },
  Mia_benh_kham_la: { crop: "Mía", disease: "Bệnh khảm lá" },
  Mia_benh_ri_sat_nau: { crop: "Mía", disease: "Bệnh rỉ sắt nâu" },
  Mia_benh_than_den: { crop: "Mía", disease: "Bệnh than đen" },
  Mia_benh_thoi_hom: { crop: "Mía", disease: "Bệnh thối hom" },
  Mia_benh_vang_la: { crop: "Mía", disease: "Bệnh vàng lá" },
  Mia_khoe_manh: { crop: "Mía", disease: "Khỏe mạnh" },
  Mia_la_kho: { crop: "Mía", disease: "Bệnh lá khô" },
  Ngo_benh_chay_la_lon: { crop: "Ngô", disease: "Bệnh cháy lá lớn" },
  Ngo_benh_dom_la_xam: { crop: "Ngô", disease: "Bệnh đốm lá xám" },
  Ngo_benh_ri_sat: { crop: "Ngô", disease: "Bệnh rỉ sắt" },
  Ngo_khoe_manh: { crop: "Ngô", disease: "Khỏe mạnh" },
};

/** Fallback: split class id on "_" when it is not in the lookup table. */
function fallbackLabel(cls: string): DiseaseLabel {
  const parts = cls.split("_");
  const crop = CROP_LABEL[parts[0]?.toLowerCase()] ?? parts[0] ?? "";
  const rest = parts.slice(1).join(" ").replace(/___/g, " ").trim();
  const disease = !rest || rest === "khoe manh" || rest === "healthy"
    ? "Khỏe mạnh"
    : rest.charAt(0).toUpperCase() + rest.slice(1);
  return { crop, disease };
}

function lookup(cls: string): DiseaseLabel {
  return DISEASE_LABELS[cls] ?? fallbackLabel(cls);
}

/** Vietnamese disease name only, e.g. "Bệnh đạo ôn cổ bông". */
export function getDiseaseName(cls: string): string {
  if (!cls || cls === "model_not_loaded") return "Chưa xác định";
  return lookup(cls).disease;
}

/** Vietnamese crop name only, e.g. "Lúa". */
export function getCropName(cls: string): string {
  if (!cls || cls === "model_not_loaded") return "—";
  return lookup(cls).crop;
}

/** Combined label "Lúa — Bệnh đạo ôn cổ bông". */
export function formatDiseaseName(cls: string): string {
  if (!cls || cls === "model_not_loaded") return "Chưa xác định";
  const { crop, disease } = lookup(cls);
  return `${crop} — ${disease}`;
}
