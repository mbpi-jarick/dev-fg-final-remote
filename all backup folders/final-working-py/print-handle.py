# Make sure to import these at the top of your file
from datetime import datetime
from PyQt6.QtGui import QPainter, QFont, QPen, QFontMetrics
from PyQt6.QtWidgets import QMessageBox
from PyQt6.QtCore import QRectF, Qt


# NOTE: This code assumes you are using PyQt5.
# If you are using PyQt6 or PySide6, you may need to adjust the imports, e.g.:
# from PyQt6.QtGui import QPainter, QFont, QPen, QFontMetrics
# from PyQt6.QtCore import QRectF, Qt
# and change things like QFont.Weight.Bold to QFont.Bold

def _handle_paint_request(self, printer):
    painter = QPainter()
    if not painter.begin(printer):
        QMessageBox.critical(self, "Print Error", "Could not initialize painter.")
        return

    # --- LAYOUT CONSTANTS (in Points: 72 points = 1 inch) ---
    MARGIN = 36
    PADDING = 5
    PAGE_RECT = printer.pageRect(QPrinter.Unit.Point)
    CONTENT_RECT = PAGE_RECT.adjusted(MARGIN, MARGIN, -MARGIN, -MARGIN)
    # Reserve space at the bottom for the final footer line and page-end summary
    FOOTER_RESERVED_HEIGHT = 150

    # --- FONT DEFINITIONS ---
    header_font = QFont("Arial", 11, QFont.Weight.Bold)
    title_font = QFont("Arial", 14, QFont.Weight.Bold)
    bold_font = QFont("Arial", 9, QFont.Weight.Bold)
    normal_font = QFont("Arial", 9)
    small_font = QFont("Arial", 8)
    small_bold_font = QFont("Arial", 8, QFont.Weight.Bold)
    footer_font = QFont("Arial", 7)
    important_font = QFont("Arial", 6)

    # --- DATA GATHERING ---
    primary_data = {
        "dr_no": self.dr_no_edit.text(), "delivery_date": self.delivery_date_edit.date().toString("MM/dd/yyyy"),
        "charge_to": self.customer_combo.currentText(), "deliver_to": self.deliver_to_edit.text(),
        "address": self.address_edit.text(), "po_no": self.po_no_edit.text(), "terms": self.terms_edit.text(),
        "prepared_by": self.prepared_by_label.text(), "encoded_on": datetime.now().strftime("%y/%m/%d %I:%M:%S %p")
    }
    # Assuming _get_item_data_from_row fetches price and calculates amount
    items_data = [self._get_item_data_from_row(row) for row in range(self.items_table.rowCount())]

    # --- HELPER FUNCTIONS ---
    def draw_page_header(p, y_start):
        p.setFont(header_font)
        p.drawText(QRectF(0, y_start, PAGE_RECT.width(), 20), Qt.AlignmentFlag.AlignHCenter,
                   "MASTERBATCH PHILIPPINES INC.")
        y_start += 18
        p.setFont(normal_font)
        p.drawText(QRectF(0, y_start, PAGE_RECT.width(), 15), Qt.AlignmentFlag.AlignHCenter,
                   "24 Diamond Road Caloocan Industrial Subdivision, Bo. Kaybiga, Caloocan City, Philippines")
        y_start += 15
        p.drawText(QRectF(0, y_start, PAGE_RECT.width(), 15), Qt.AlignmentFlag.AlignHCenter,
                   "Tel. Nos.: 8935-9579 / 7758-1207 | Telefax: 8374-7085")
        y_start += 15
        p.drawText(QRectF(0, y_start, PAGE_RECT.width(), 15), Qt.AlignmentFlag.AlignHCenter, "TIN NO.: 238-034-470-000")
        y_start += 25
        p.setFont(title_font)
        p.drawText(QRectF(0, y_start, PAGE_RECT.width(), 20), Qt.AlignmentFlag.AlignHCenter, "DELIVERY RECEIPT")
        y_start += 30
        return y_start

    def draw_table_header(p, y_start, cols):
        p.setPen(QPen(Qt.GlobalColor.black, 1))
        header_height = 20
        p.setFont(small_bold_font)
        p.drawText(QRectF(cols['qty'], y_start, cols['unit'] - cols['qty'], header_height),
                   Qt.AlignmentFlag.AlignCenter, "QUANTITY")
        p.drawText(QRectF(cols['unit'], y_start, cols['desc'] - cols['unit'], header_height),
                   Qt.AlignmentFlag.AlignCenter, "UNIT")
        p.drawText(QRectF(cols['desc'], y_start, cols['price'] - cols['desc'], header_height),
                   Qt.AlignmentFlag.AlignCenter, "DESCRIPTION")
        p.drawText(QRectF(cols['price'], y_start, cols['amount'] - cols['price'], header_height),
                   Qt.AlignmentFlag.AlignCenter, "UNIT PRICE")
        p.drawText(QRectF(cols['amount'], y_start, CONTENT_RECT.right() - cols['amount'], header_height),
                   Qt.AlignmentFlag.AlignCenter, "AMOUNT")
        p.drawLine(CONTENT_RECT.left(), y_start + header_height, CONTENT_RECT.right(), y_start + header_height)
        return y_start + header_height + PADDING

    # ===================================================================
    # --- RENDER THE DOCUMENT - PAGE 1 ---
    # ===================================================================
    y = MARGIN
    y = draw_page_header(painter, y)
    y += PADDING * 2

    # --- CUSTOMER & DR INFO SECTION (DYNAMIC HEIGHT) ---
    fm_normal = QFontMetrics(normal_font)
    fm_bold = QFontMetrics(bold_font)

    # Calculate height of left (address) side
    address_rect = QRectF(MARGIN + 70, 0, 200, 500)  # Use a very tall rect for calculation
    address_bounding_rect = fm_normal.boundingRect(address_rect, Qt.TextFlag.TextWordWrap, primary_data['address'])
    left_height = 45 + address_bounding_rect.height()

    # Right side height is simpler (4 static lines)
    right_height = 4 * (fm_normal.height() + PADDING)

    section_height = max(left_height, right_height)
    info_y_start = y

    painter.setFont(small_font);
    painter.drawText(MARGIN, info_y_start, "Customer's Name/Address")

    # Left side (Customer)
    painter.setFont(normal_font);
    painter.drawText(MARGIN + PADDING, info_y_start + 15, "Charge to:")
    painter.drawText(MARGIN + PADDING, info_y_start + 30, "Deliver to:")
    painter.drawText(MARGIN + PADDING, info_y_start + 45, "Address:")
    painter.setFont(bold_font)
    painter.drawText(MARGIN + 70, info_y_start + 15, primary_data['charge_to'])
    painter.drawText(MARGIN + 70, info_y_start + 30, primary_data['deliver_to'])
    painter.setFont(normal_font)  # Address is normal font
    painter.drawText(QRectF(MARGIN + 70, info_y_start + 45, 200, 40), Qt.TextFlag.TextWordWrap, primary_data['address'])

    # Right side (DR Details)
    dr_info_x = MARGIN + 280
    painter.setFont(bold_font);
    painter.drawText(dr_info_x, info_y_start, "No.:")
    painter.setFont(QFont("Arial", 11, QFont.Weight.Bold));
    painter.drawText(dr_info_x + 30, info_y_start, primary_data['dr_no'])
    painter.setFont(normal_font);
    painter.drawText(dr_info_x, info_y_start + 15, "Delivery Date:")
    painter.drawText(dr_info_x, info_y_start + 30, "PO No.:")
    painter.drawText(dr_info_x, info_y_start + 45, "Terms of Payment:")
    painter.setFont(bold_font)
    painter.drawText(dr_info_x + 90, info_y_start + 15, primary_data['delivery_date'])
    painter.drawText(dr_info_x + 90, info_y_start + 30, primary_data['po_no'])
    painter.drawText(dr_info_x + 90, info_y_start + 45, primary_data['terms'])

    y += section_height + PADDING * 4

    # --- ITEMS TABLE (DYNAMIC WITH PAGE BREAKS) ---
    col_x = {
        "qty": CONTENT_RECT.left(),
        "unit": CONTENT_RECT.left() + 60,
        "desc": CONTENT_RECT.left() + 100,
        "price": CONTENT_RECT.left() + 320,  # 220 for desc
        "amount": CONTENT_RECT.left() + 382  # 62 for price
    }

    # Draw table outline and headers for the first time
    y = draw_table_header(painter, y, col_x)

    table_content_bottom_boundary = PAGE_RECT.height() - MARGIN - FOOTER_RESERVED_HEIGHT

    painter.setFont(normal_font)
    fm_items = QFontMetrics(normal_font)

    for item in items_data:
        # --- 1. PREPARE DATA FOR ALL COLUMNS ---
        try:
            qty_val = float(item.get("quantity", 0))
            price_val = float(item.get("unit_price", 0))
            amount_val = qty_val * price_val
        except (ValueError, TypeError):
            qty_val, price_val, amount_val = 0.0, 0.0, 0.0

        qty_text = f"{qty_val:.2f}"
        unit_text = item.get('unit', '')
        price_text = f"{price_val:,.2f}"
        amount_text = f"{amount_val:,.2f}"

        desc_parts = [
            f"{item.get('product_code', '')} {item.get('product_color', '')}",
            f"{item.get('no_of_packing')} Bag(s) by {item.get('weight_per_pack')} KG." if item.get(
                'no_of_packing') and item.get('weight_per_pack') else None,
            f"LOT #{item.get('lot_numbers')}" if item.get('lot_numbers') else None,
            item.get('attachments')
        ]
        desc_text = "\n".join(filter(None, desc_parts))

        # --- 2. CALCULATE REQUIRED ROW HEIGHT ---
        desc_width = col_x['price'] - col_x['desc'] - PADDING
        desc_calc_rect = QRectF(0, 0, desc_width, 500)
        desc_bounding_rect = fm_items.boundingRect(desc_calc_rect, Qt.TextFlag.TextWordWrap, desc_text)
        row_height = max(fm_items.height() + PADDING, desc_bounding_rect.height() + PADDING)

        # --- 3. CHECK FOR PAGE BREAK ---
        if y + row_height > table_content_bottom_boundary and items_data.index(item) > 0:
            printer.newPage()
            y = MARGIN
            y = draw_page_header(painter, y)
            y += PADDING * 6  # More space after header on subsequent pages
            y = draw_table_header(painter, y, col_x)
            painter.setFont(normal_font)  # Reset font after header drawing

        # --- 4. DRAW THE ROW ---
        painter.drawText(QRectF(col_x['qty'], y, col_x['unit'] - col_x['qty'], row_height),
                         Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter, qty_text)
        painter.drawText(QRectF(col_x['unit'], y, col_x['desc'] - col_x['unit'], row_height),
                         Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter, unit_text)
        painter.drawText(QRectF(col_x['desc'] + PADDING, y, desc_width, row_height),
                         Qt.TextFlag.TextWordWrap | Qt.AlignmentFlag.AlignVCenter, desc_text)
        painter.drawText(QRectF(col_x['price'], y, col_x['amount'] - col_x['price'], row_height),
                         Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, price_text + "  ")
        painter.drawText(QRectF(col_x['amount'], y, CONTENT_RECT.right() - col_x['amount'], row_height),
                         Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, amount_text + "  ")

        y += row_height  # Advance y by the calculated height of the row

    # --- END OF TABLE ---
    painter.setPen(QPen(Qt.GlobalColor.black, 1))
    painter.drawLine(CONTENT_RECT.left(), y, CONTENT_RECT.right(), y)
    y += PADDING
    painter.setFont(bold_font)
    painter.drawText(QRectF(CONTENT_RECT.left(), y, CONTENT_RECT.width(), 20), Qt.AlignmentFlag.AlignHCenter,
                     "***************** NOTHING FOLLOWS *****************")
    y += fm_bold.height() + PADDING * 4

    # --- DYNAMICALLY PLACED FOOTER ---
    painter.setPen(QPen(Qt.GlobalColor.black, 1))
    painter.setFont(normal_font)
    painter.drawText(MARGIN, y, "Delivery Time In: _________________")
    painter.drawText(MARGIN + 220, y, "Delivery Time Out: _________________")
    y += fm_normal.height() + PADDING
    painter.drawText(MARGIN, y, "Received the above items in good order and condition.")
    y += fm_normal.height() * 2

    painter.drawText(MARGIN + 300, y, "By: ________________________________")
    y += fm_normal.height()
    painter.drawText(MARGIN + 340, y, "Signature over printed Name/Date")
    y += fm_normal.height() * 2

    painter.setFont(important_font)
    important_text = "IMPORTANT: Merchandise described in this Delivery Receipt remains the property of MASTERBATCH PHILIPPINES, INC. until fully paid. Interest of 18% per annum is to be charged on all overdue accounts. An additional sum equal to 25% of the amount will be charged by the vendor or attorney's fees and cost of collection in case of suit. Parties expressly submit themselves to the jurisdiction of the courts of MANILA in any legal action arising from the transaction."
    painter.drawText(QRectF(MARGIN, y, 280, 60), Qt.AlignmentFlag.AlignLeft | Qt.TextFlag.TextWordWrap, important_text)

    # --- ABSOLUTE FOOTER (at bottom of page) ---
    painter.setFont(footer_font)
    painter.drawText(MARGIN, PAGE_RECT.height() - MARGIN,
                     f"//{primary_data['dr_no']}/{primary_data['encoded_on']}/{primary_data['prepared_by']}")

    painter.end()