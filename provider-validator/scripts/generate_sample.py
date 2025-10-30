import csv, random
from faker import Faker

fake = Faker()

def gen_row(i):
    name = fake.name()
    return {
        "id": i+1,
        "name": name,
        "npi": str(1000000000 + i),
        "phone": fake.phone_number(),
        "address": fake.address().replace("\n", ", "),
        "website": fake.domain_name(),
        "specialty": random.choice(["Cardiology","Family Medicine","Dermatology","Orthopedics"]),
        "scanned_pdf": f"data/scanned_pdfs/sample_{i%5 +1}.pdf"  # reuse 5 sample PDFs
    }

with open("data/providers_sample.csv", "w", newline='') as f:
    writer = csv.DictWriter(f, fieldnames=list(gen_row(0).keys()))
    writer.writeheader()
    for i in range(200):
        writer.writerow(gen_row(i))

print("Synthetic CSV generated at data/providers_sample.csv")
