"""CampusBite data models — single source of truth for menu schema validation."""
from __future__ import annotations

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


class Category(str, Enum):
    breakfast = "breakfast"
    main_course = "main_course"
    snack = "snack"
    beverage = "beverage"
    dessert = "dessert"
    combo = "combo"


class Cuisine(str, Enum):
    south_indian = "south_indian"
    north_indian = "north_indian"
    chinese = "chinese"
    continental = "continental"
    street_food = "street_food"


class Allergen(str, Enum):
    peanuts = "peanuts"
    tree_nuts = "tree_nuts"
    dairy = "dairy"
    gluten = "gluten"
    soy = "soy"
    egg = "egg"
    seafood = "seafood"
    sesame = "sesame"


class DietaryTag(str, Enum):
    veg = "veg"
    non_veg = "non_veg"
    vegan = "vegan"
    egg = "egg"
    jain = "jain"
    gluten_free = "gluten_free"
    dairy_free = "dairy_free"
    halal = "halal"


class PortionSize(str, Enum):
    light = "light"
    medium = "medium"
    heavy = "heavy"
    filling = "filling"


class ServingTime(str, Enum):
    breakfast = "breakfast"
    lunch = "lunch"
    dinner = "dinner"
    all_day = "all_day"


TASTE_PROFILES = {"sweet", "spicy", "tangy", "savory", "cheesy", "refreshing", "comforting"}
MOOD_TAGS = {"energizing", "comfort", "light", "indulgent", "study_fuel", "homesick", "celebratory"}


class MenuItem(BaseModel):
    id: str = Field(..., description="slug unique id")
    name: str
    description: str = ""
    price: float = Field(..., ge=0, description="price in INR")
    category: Category
    cuisine: Cuisine
    ingredients: List[str] = Field(default_factory=list)
    allergens: List[Allergen] = Field(default_factory=list)
    dietary_tags: List[DietaryTag] = Field(default_factory=list)
    availability: bool = True
    available_until: Optional[str] = Field(
        default=None, description="HH:MM 24h — simulate real-time stock window, None = all day"
    )
    prep_time_minutes: int = Field(..., ge=2, le=25)
    calories: int = Field(..., ge=0)
    protein_g: int = Field(default=0, ge=0, description="protein grams (for gym/diet goals)")
    carbs_g: int = Field(default=0, ge=0, description="carbs grams, estimated (for diabetic/low-carb goals)")
    sugar_g: int = Field(default=0, ge=0, description="sugar grams, estimated incl. natural sugars")
    fiber_g: int = Field(default=0, ge=0, description="fiber grams, estimated")
    portion_size: PortionSize
    spice_level: int = Field(..., ge=0, le=3)
    taste_profile: List[str] = Field(default_factory=list)
    mood_tags: List[str] = Field(default_factory=list)
    serving_times: List[ServingTime] = Field(default_factory=list)
    popularity_score: int = Field(..., ge=0, le=100)
    is_combo: bool = False
    combo_items: List[str] = Field(default_factory=list)

    def model_post_init(self, __context) -> None:
        # Lightweight domain validation beyond pydantic types.
        for t in self.taste_profile:
            if t not in TASTE_PROFILES:
                raise ValueError(f"Unknown taste_profile '{t}' on item {self.id}")
        for m in self.mood_tags:
            if m not in MOOD_TAGS:
                raise ValueError(f"Unknown mood_tag '{m}' on item {self.id}")
        if self.is_combo and not self.combo_items:
            raise ValueError(f"Combo item {self.id} must list combo_items")
        if not self.is_combo and self.combo_items:
            raise ValueError(f"Non-combo item {self.id} must not list combo_items")
        # Jain invariant: no onion/garlic in ingredients (checked case-insensitively).
        if DietaryTag.jain in self.dietary_tags:
            lowered = [i.lower() for i in self.ingredients]
            if any("onion" in i or "garlic" in i for i in lowered):
                raise ValueError(f"Jain item {self.id} must not contain onion/garlic")


class UserPreferences(BaseModel):
    """Normalized preferences produced by NLU layer, consumed by recommender."""

    budget: Optional[float] = Field(default=None, ge=0)
    max_prep_time: Optional[int] = Field(default=None, ge=0)
    mood: Optional[str] = None
    dietary_restrictions: List[str] = Field(default_factory=list)  # e.g. ["veg","vegan","jain","gluten_free","halal","egg_free"]
    allergies: List[Allergen] = Field(default_factory=list)
    cravings: List[str] = Field(default_factory=list)  # taste keywords
    hunger: Optional[str] = None  # light_bite / medium / hungry / very_hungry
    meal: Optional[str] = None  # breakfast / lunch / dinner / None=auto
    cuisine: Optional[str] = None
    max_spice: Optional[int] = None
    combos_only: bool = False
    no_onion_garlic: bool = False
    avoid: List[str] = Field(default_factory=list, description="food words to exclude (without/don't want)")
    goal: Optional[str] = None  # high_protein / low_calorie / diabetic / period_friendly / None
