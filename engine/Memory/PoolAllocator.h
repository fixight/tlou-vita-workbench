#include <cstdint>
#include <cstdlib>
#include <vector>
// На Vita лучше подключать malloc.h для доступа к memalign
#include <malloc.h>

struct MetaData {
    size_t nextAvailableIndex = 0;
    uint8_t* memory = nullptr;
};

class PoolAllocator {
private:
    uint8_t* m_buffer = nullptr;
    size_t firstAvailable = 0;
    size_t blockSize = 0;
    size_t capacity = 0;
    std::vector<MetaData> blocks;

public:
    PoolAllocator(size_t count, size_t size) {
        capacity = count;
        firstAvailable = 0;

        // 1. ВЫРАВНИВАНИЕ РАЗМЕРА БЛОКА (Округление до 16 байт)
        // Если size = 33, то blockSize станет 48.
        // Формула: (size + (align - 1)) & ~(align - 1)
        size_t alignment = 16;
        blockSize = (size + alignment - 1) & ~(alignment - 1);

        // 2. ВЫДЕЛЕНИЕ ВЫРОВНЕННОЙ ПАМЯТИ
        // На PS Vita стандартный malloc часто выравнивает по 8 байт.
        // Для 3D графики и матриц GLM надежнее использовать memalign(16, ...).
        // (Если эмулятор/ПК ругается на memalign, используйте обычный malloc,
        // но на самой Вите лучше использовать memalign)
#if defined(_WIN32) // Если компилируете на ПК
        m_buffer = static_cast<uint8_t*>(_aligned_malloc(count * blockSize, alignment));
#else // Для PS Vita (GCC / Clang)
        m_buffer = static_cast<uint8_t*>(memalign(alignment, count * blockSize));
#endif

        blocks.reserve(count);

        for (size_t i = 0; i < count; ++i) {
            MetaData data;
            data.nextAvailableIndex = i + 1;

            // Теперь каждый шаг равен blockSize (который кратен 16).
            // Память всегда будет идеально ровной!
            data.memory = m_buffer + (blockSize * i);
            blocks.push_back(data);
        }
    }

    ~PoolAllocator() {
        if (m_buffer) {
#if defined(_WIN32)
            _aligned_free(m_buffer);
#else
            free(m_buffer); // free нормально съедает указатели от memalign
#endif
        }
    }

    template<typename T>
    T* Allocate(size_t& outBlockID) {
        // Проверяем против НОВОГО размера блока
        if (sizeof(T) > blockSize || firstAvailable >= capacity) {
            return nullptr;
        }

        outBlockID = firstAvailable;
        uint8_t* memory = blocks[firstAvailable].memory;
        firstAvailable = blocks[firstAvailable].nextAvailableIndex;

        return reinterpret_cast<T*>(memory);
    }

    void Clear(size_t blockID) {
        if (blockID >= capacity) return;

        size_t oldFirst = firstAvailable;
        firstAvailable = blockID;
        blocks[blockID].nextAvailableIndex = oldFirst;
    }
};