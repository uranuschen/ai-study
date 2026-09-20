prices = [300, 800, 1200, 450, 600]

def get_final_price(price, vip):

    if vip:
        price -= 100

    if price >= 500:
        price -= 50

    return price


total = 0

for price in prices:
    final_price = get_final_price(price, True)
    total += final_price

print(total)