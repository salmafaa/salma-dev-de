# run_scraper.py
import asyncio
from src.scraper import scrape_hotel_images, HotelNotFoundError


async def main():
    hotels = [
        ("Grand Hyatt Jakarta", "Jakarta"),
        ("Vio Cihampelas", "Bandung"),
        ("The Westin Resort Nusa Dua", "Bali"),
    ]

    for hotel_name, city in hotels:
        print(f"\nMencari gambar: {hotel_name} di {city}...")
        try:
            paths = await scrape_hotel_images(
                hotel_name=hotel_name,
                city=city,
                output_dir="./output_images",
                max_images=3,
            )
            print(f"Berhasil! {len(paths)} gambar tersimpan:")
            for p in paths:
                print(f"  {p}")
        except HotelNotFoundError as e:
            print(f"Hotel tidak ditemukan: {e}")
        except Exception as e:
            print(f"Error: {e}")


if __name__ == "__main__":
    asyncio.run(main())