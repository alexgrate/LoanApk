from .models import PRODUCTS


def navigation(request):
    return {
        "nav_products": [(code, model.PRODUCT_LABEL) for code, model in PRODUCTS.items()]
    }
