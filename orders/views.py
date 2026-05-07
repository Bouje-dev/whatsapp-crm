"""
Order list (HTMX), export, import, and inline update views.
"""
import csv
import io
from collections import Counter

from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.paginator import Paginator
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.generic import ListView
from django.views.decorators.http import require_http_methods, require_GET, require_POST
from django.contrib.auth import get_user_model

from .models import Order, Store
from .filters import OrderFilter, SOURCE_PLATFORM_CHOICES
from .services import bulk_assign_orders
from discount.activites import log_activity

try:
    from discount.whatssapAPI.views import get_target_channel
except ImportError:
    get_target_channel = None

User = get_user_model()

PAGINATE_BY = 15


def _get_base_queryset(request):
    return Order.objects.for_user(request.user).select_related(
        "store", "assigned_agent", "attribution_data" 
    )


class OrderListView(LoginRequiredMixin, ListView):
    model = Order
    template_name = "orders/order_list.html"
    context_object_name = "orders"
    paginate_by = 50

    def get_queryset(self):
        qs = _get_base_queryset(self.request)
        self.filterset = OrderFilter(self.request.GET, queryset=qs)
        return self.filterset.qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["filter"] = self.filterset
        ctx["agents"] = User.objects.filter(is_active=True).order_by("username")
        ctx["status_choices"] = Order.STATUS_CHOICES
        ctx["source_choices"] = SOURCE_PLATFORM_CHOICES
        ch = get_target_channel(self.request.user, None) if get_target_channel else None
        ctx["default_channel_id"] = ch.id if ch else None
        return ctx


@login_required
def order_table_partial(request):
    """HTMX: return only the table + pagination for swapping."""
    qs = _get_base_queryset(request)
    filterset = OrderFilter(request.GET, queryset=qs)
    paginator = Paginator(filterset.qs, PAGINATE_BY)
    page_number = request.GET.get("page", 1)
    try:
        page_number = max(1, int(page_number))
    except (TypeError, ValueError):
        page_number = 1
    page_obj = paginator.get_page(page_number)
    # Query params for pagination links (without page)
    get_copy = request.GET.copy()
    get_copy.pop("page", None)
    base_query = get_copy.urlencode()
    agents = User.objects.filter(is_active=True).order_by("username")
    return render(
        request,
        "orders/partials/order_table.html",
        {
            "orders": page_obj.object_list,
            "page_obj": page_obj,
            "base_query": base_query,
            "agents": agents,
            "status_choices": Order.STATUS_CHOICES,
        },
    )


@login_required
@require_http_methods(["POST"])
def order_update_status(request, pk):
    """HTMX: inline update of order status (hx-post)."""
    order = get_object_or_404(Order, pk=pk)
    qs = Order.objects.for_user(request.user)
    if not qs.filter(pk=pk).exists():
        return HttpResponse("", status=403)
    new_status = (request.POST.get("status") or "").strip()
    if new_status in dict(Order.STATUS_CHOICES):
        old_status = order.status
        order.status = new_status
        order.save()
        log_activity(
            'order_status_changed',
            f"Order #{order.pk} status: {old_status} → {new_status} (phone: {order.phone})",
            request=request, related_object=order,
        )
    return render(
        request,
        "orders/partials/order_row.html",
        {"order": order, "agents": User.objects.filter(is_active=True).order_by("username"), "status_choices": Order.STATUS_CHOICES},
    )


@login_required
@require_http_methods(["POST"])
def order_update_agent(request, pk):
    """HTMX: inline update of assigned agent."""
    order = get_object_or_404(Order, pk=pk)
    qs = Order.objects.for_user(request.user)
    if not qs.filter(pk=pk).exists():
        return HttpResponse("", status=403)
    agent_id = request.POST.get("assigned_agent")
    old_agent = order.assigned_agent
    if agent_id == "" or agent_id is None:
        order.assigned_agent = None
    else:
        agent = User.objects.filter(pk=agent_id).first()
        if agent:
            order.assigned_agent = agent
    order.save()
    log_activity(
        'order_agent_changed',
        f"Order #{order.pk} agent: {old_agent or 'None'} → {order.assigned_agent or 'None'}",
        request=request, related_object=order,
    )
    return render(
        request,
        "orders/partials/order_row.html",
        {"order": order, "agents": User.objects.filter(is_active=True).order_by("username"), "status_choices": Order.STATUS_CHOICES},
    )


@login_required
@require_http_methods(["POST"])
def order_bulk_assign(request):
    """Bulk assign selected orders to an agent. Redirects back to list with same filters."""
    order_ids_raw = request.POST.getlist("order_ids") or request.POST.get("order_ids", "").replace(" ", "").split(",")
    order_ids = [x for x in order_ids_raw if str(x).isdigit()]
    agent_id = request.POST.get("agent_id") or None
    if not order_ids:
        return HttpResponse("No orders selected", status=400)
    bulk_assign_orders([int(x) for x in order_ids], agent_id, request.user)
    agent_name = User.objects.filter(pk=agent_id).values_list('username', flat=True).first() if agent_id else 'None'
    log_activity(
        'order_bulk_assign',
        f"Bulk assigned {len(order_ids)} orders to {agent_name}",
        request=request,
    )
    # Redirect back with current filters
    params = {}
    if request.POST.get("status"):
        params["status"] = request.POST["status"]
    if request.POST.get("source"):
        params["source"] = request.POST["source"]
    if request.POST.get("phone"):
        params["phone"] = request.POST["phone"]
    if request.POST.get("date_after"):
        params["date_after"] = request.POST["date_after"]
    if request.POST.get("date_before"):
        params["date_before"] = request.POST["date_before"]
    url = reverse("orders:order_list")
    if params:
        from urllib.parse import urlencode
        url += "?" + urlencode(params)
    return redirect(url)


@login_required
@require_GET
def order_export(request):
    """Export filtered order list as CSV. Uses same filters as list (status, source, phone, dates)."""
    qs = _get_base_queryset(request)
    filterset = OrderFilter(request.GET, queryset=qs)
    orders = filterset.qs[:10000]
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="orders_export.csv"'
    writer = csv.writer(response)
    writer.writerow(["Date", "Customer", "Phone", "Address", "Product", "Quantity", "Status", "Source", "Agent"])
    for o in orders:
        source = (o.attribution_data.utm_source if o.attribution_data else "") or ""
        agent = (o.assigned_agent.get_full_name() or o.assigned_agent.username) if o.assigned_agent else ""
        writer.writerow([
            o.created_at.strftime("%Y-%m-%d %H:%M") if o.created_at else "",
            o.name or "",
            o.phone or "",
            (o.address or "")[:500],
            o.product_name or "",
            o.quantity,
            o.status or "",
            source,
            agent,
        ])
    return response


def _normalize_csv_row(row):
    """Return dict with lowercase keys and stripped values."""
    return {str(k).strip().lower().replace(" ", "_"): (v.strip() if v is not None else "") for k, v in row.items()}


def _row_key(row):
    """Key for duplicate check: (phone, product_name, name)."""
    phone = (row.get("phone") or row.get("phone_number") or "").strip()
    product = (row.get("product_name") or row.get("product") or "").strip()
    name = (row.get("name") or row.get("customer_name") or row.get("customer") or "").strip()
    return (phone, product, name)


def _normalize_import_status(raw):
    """Map CSV status value or label to Order.STATUS_* if valid."""
    if not raw or not str(raw).strip():
        return None
    raw_upper = str(raw).strip().upper().replace(" ", "_")
    valid = dict(Order.STATUS_CHOICES)
    if raw_upper in valid:
        return raw_upper
    for key, label in valid.items():
        if key == raw_upper or key.replace("_", "") == raw_upper.replace("_", ""):
            return key
        if (label or "").upper().replace(" ", "_") == raw_upper:
            return key
    return None


@login_required
@require_POST
def order_import(request):
    """
    Import orders from CSV. Expects columns: name/customer_name, phone, product_name/product, address (optional), status (optional).
    If the same (phone, product_name, name) appears more than 2 times in the file, none of those rows are saved.
    If name+phone already exist for this user's orders: update that order's status (and product/address) if changed.
    Returns JSON: { saved: N, updated: U, duplicated: M }.
    """
    f = request.FILES.get("file")
    if not f:
        return JsonResponse({"error": "No file uploaded"}, status=400)
    if not f.name.lower().endswith(".csv"):
        return JsonResponse({"error": "File must be a CSV"}, status=400)
    try:
        content = f.read().decode("utf-8-sig").strip()
    except Exception:
        return JsonResponse({"error": "Could not read file as UTF-8"}, status=400)
    reader = csv.DictReader(io.StringIO(content))
    rows = []
    for r in reader:
        nr = _normalize_csv_row(r)
        if not nr:
            continue
        rows.append(nr)
    key_counts = Counter(_row_key(r) for r in rows)
    keys_over_two = {k for k, c in key_counts.items() if c > 2}
    to_save = [r for r in rows if _row_key(r) not in keys_over_two]
    duplicated_count = sum(key_counts[k] for k in keys_over_two)
    saved_count = 0
    updated_count = 0
    store = None
    owner = request.user
    qs_user = Order.objects.for_user(owner)
    for r in to_save:
        name = (r.get("name") or r.get("customer_name") or r.get("customer") or "—").strip()[:255]
        phone = (r.get("phone") or r.get("phone_number") or "—").strip()[:32]
        product_name = (r.get("product_name") or r.get("product") or "—").strip()[:255]
        address = (r.get("address") or "").strip()[:2000]
        import_status = _normalize_import_status(r.get("status"))
        if not name or name == "—":
            name = "—"
        if not phone or phone == "—":
            phone = "—"
        if not product_name or product_name == "—":
            product_name = "—"
        existing = qs_user.filter(name=name, phone=phone).order_by("-created_at").first()
        if existing:
            changed = False
            if import_status and existing.status != import_status:
                existing.status = import_status
                changed = True
            if product_name and product_name != "—" and existing.product_name != product_name:
                existing.product_name = product_name
                changed = True
            if address is not None and existing.address != address:
                existing.address = address
                changed = True
            if changed:
                existing.save()
                updated_count += 1
            continue
        if store is None:
            store, _ = Store.objects.get_or_create(owner=owner, defaults={"name": "Default Store"})
        Order.objects.create(
            name=name,
            phone=phone,
            address=address,
            product_name=product_name,
            store=store,
            status=import_status or Order.STATUS_NEW,
        )
        saved_count += 1
    log_activity(
        'order_imported',
        f"Imported orders: {saved_count} new, {updated_count} updated, {duplicated_count} duplicated",
        request=request,
    )
    return JsonResponse({"saved": saved_count, "updated": updated_count, "duplicated": duplicated_count})
