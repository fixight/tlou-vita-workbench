#ifndef TLOU_VITA_ARENAALLOCATOR_H
#define TLOU_VITA_ARENAALLOCATOR_H

#include <cstdint>
#include <cstdlib>
#include <iostream>
#include <psp2/kernel/clib.h>

class ArenaAllocator {
private:
    uint8_t* m_buffer = nullptr;
    size_t m_capacity = 0;
    size_t m_offset = 0;

public:
    // Конструктор: выделяет один большой кусок памяти
    ArenaAllocator(size_t bytes) {
        m_capacity = bytes;
        m_buffer = static_cast<uint8_t*>(malloc(bytes));

        // Проверка успешности выделения памяти:
        if (m_buffer == nullptr) {
            sceClibPrintf("[CRITICAL ERROR] malloc(%u bytes) FAILED! Vita heap is exhausted!\n", (uint32_t)bytes);
            m_capacity = 0;
        } else {
            sceClibPrintf("[SUCCESS] ArenaAllocator created with %u MB\n", (uint32_t)(bytes / (1024 * 1024)));
        }
    }

    //ИСПРАВЛЕНО: Добавлен знак ~ (Деструктор очищает память при выходе)
    ~ArenaAllocator() {
        if (m_buffer) {
            free(m_buffer);
        }
    }

    // 1. Выделение СЫРЫХ БАЙТ произвольного размера (для текстур, звуков, блоков)
    void* allocateBytes(size_t sizeInBytes) {
        // Защита: влезет ли запрос в оставшуюся память?
        if (m_offset + sizeInBytes > m_capacity) {
            std::cerr << "[ArenaAllocator] Ошибка: Память переполнена! Запрошено: "
                      << sizeInBytes << " байт, осталось: "
                      << (m_capacity - m_offset) << " байт." << std::endl;
            return nullptr;
        }

        uint8_t* currentAddress = m_buffer + m_offset;
        m_offset += sizeInBytes; // Сдвигаем указатель вперед

        return currentAddress;
    }

    // 2. Выделение МАССИВА объектов указанного типа (например, 7650 вершин)
    template<typename T>
    T* allocate(size_t count = 1) {
        size_t totalBytes = sizeof(T) * count;
        return static_cast<T*>(allocateBytes(totalBytes));
    }

    // Сброс всей арены в 0 за один такт!
    void FreeMemory() {
        m_offset = 0;
    }

    // Вспомогательные методы для контроля памяти
    // Вызывается владельцем арены после завершения всех записей в её буферы.
    void Rewind(size_t marker) {
        if (marker <= m_offset) m_offset = marker;
    }

    size_t getCapacity() const { return m_capacity; }
    size_t getUsedMemory() const { return m_offset; }
    size_t getRemainingMemory() const { return m_capacity - m_offset; }
    uint8_t* getPointer() const { return m_buffer + m_offset; }
};

#endif // TLOU_VITA_ARENAALLOCATOR_H